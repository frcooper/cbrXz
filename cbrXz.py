#! /usr/bin/python3

import click
import hashlib
import logging
import os
import rarfile
import shutil
import tempfile
import zipfile
import re
import xml.etree.ElementTree as ET
from importlib import metadata as _metadata

from PIL import Image


# moved logging configuration into main; keep module-level logger
logger = logging.getLogger(__name__)

BOOK_TYPES = ['.cbr', '.rar', '.cbz', '.zip', '.cb7', '.7z', '.pdf', '.epub']
IMAGE_TYPES = ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']
# Images some readers show as pages and others skip - page numbering is ambiguous when present
UNCERTAIN_IMAGE_TYPES = ['.tif', '.tiff', '.avif', '.jxl', '.heic', '.heif', '.jp2']

# Bits per pixel for Pillow image modes
MODE_BITS = {
    '1': 1, 'L': 8, 'P': 8, 'LA': 16, 'PA': 16, 'La': 16,
    'RGB': 24, 'YCbCr': 24, 'LAB': 24, 'HSV': 24,
    'RGBA': 32, 'RGBa': 32, 'RGBX': 32, 'CMYK': 32,
    'I;16': 16, 'I;16L': 16, 'I;16B': 16, 'I;16N': 16, 'I': 32, 'F': 32,
}

# ComicInfo elements that follow <Pages> in the schema sequence
AFTER_PAGES = ['CommunityRating', 'MainCharacterOrItem', 'Review', 'GTIN']
# ComicInfo elements that follow <PageCount> in the schema sequence
AFTER_PAGECOUNT = ['LanguageISO', 'Format', 'BlackAndWhite', 'Manga', 'Characters', 'Teams',
                   'Locations', 'ScanInformation', 'StoryArc', 'StoryArcNumber', 'SeriesGroup',
                   'AgeRating', 'Pages'] + AFTER_PAGES

def insertBefore(root, el, following):
    """Insert el before the first child of root whose tag is in following, else append."""
    after = [i for i, child in enumerate(root) if child.tag in following]
    root.insert(after[0] if after else len(root), el)

ET.register_namespace('xsd', 'http://www.w3.org/2001/XMLSchema')
ET.register_namespace('xsi', 'http://www.w3.org/2001/XMLSchema-instance')

# <Page> attributes that can be checked against the image they describe
INT_ATTRS = ['ImageSize', 'ImageWidth', 'ImageHeight', 'ImageBitDepth']
STR_ATTRS = ['ImageFormat', 'ImageDpi', 'ImageHash']


class PageDataError(Exception):
    """Page data cannot be guaranteed to describe the right pages."""

def get_version() -> str:
    """Return the project version from installed package metadata.
    Falls back to a dev string when not installed (local testing).
    """
    try:
        return _metadata.version("cbrXz")
    except Exception:
        return "0.0.0-dev"

def filterBook(s: str) -> bool:
    """Return True if the book/path should be filtered out."""
    name = os.path.basename(s)
    if re.search(r"\[GER\]", name, re.IGNORECASE):
        return True
    if re.search(r"\(german\)", name, re.IGNORECASE):
        return True
    if re.search(r"\[POR\]", name, re.IGNORECASE):
        return True
    if re.search(r"\(portuguese\)", name, re.IGNORECASE):
        return True
    if re.search(r"scanlation", name, re.IGNORECASE):
        return True
    return False

def filterPage(s: str) -> bool:
    """Return True if the page/path should be filtered out as junk.
    Skips Windows/macOS junk and any content under __MACOSX.
    """
    # Normalize to forward slashes for path checks
    sp = s.replace('\\', '/').strip()
    base = os.path.basename(sp)
    if base in ('Thumbs.db', '.DS_Store'):
        return True
    # Skip anything under __MACOSX
    if sp.startswith('__MACOSX/') or '/__MACOSX/' in sp:
        return True
    return False

def isPage(s: str) -> bool:
    """Return True if the path is an image that counts as a comic page."""
    return os.path.splitext(s)[1].lower() in IMAGE_TYPES

def pageInfo(path: str) -> dict:
    """Return ComicInfo <Page> attributes describing the image at path.
    ImageSize/ImageWidth/ImageHeight/DoublePage are ComicInfo schema attributes;
    ImageFormat/ImageBitDepth/ImageDpi/ImageHash are extensions.
    """
    sha = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1 << 20), b''):
            sha.update(chunk)
    info = {'ImageSize': str(os.path.getsize(path))}
    try:
        with Image.open(path) as im:
            width, height = im.size
            info['ImageWidth'] = str(width)
            info['ImageHeight'] = str(height)
            if width > height:
                info['DoublePage'] = 'true'
            if im.format:
                info['ImageFormat'] = im.format
            if im.mode in MODE_BITS:
                info['ImageBitDepth'] = str(MODE_BITS[im.mode])
            dpi = im.info.get('dpi')
            if dpi:
                x, y = (round(float(d)) for d in dpi)
                if x > 0 and y > 0:
                    info['ImageDpi'] = str(x) if x == y else f"{x}x{y}"
    except Exception as e:  # pylint: disable=broad-except
        raise PageDataError(f"cannot read image {os.path.basename(path)}: {e}") from e
    info['ImageHash'] = sha.hexdigest()
    return info

def naturalKey(s: str) -> list:
    """Sort key matching how comic readers order page names (case-insensitive, numbers by value)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

def pageOrder(entries) -> list:
    """Return the page images among entries [(arcname, path)] in reading order.
    Raises PageDataError unless every common ordering (plain, case-insensitive,
    natural) agrees, so a page index means the same image in any reader.
    """
    uncertain = [n for n, _ in entries if os.path.splitext(n)[1].lower() in UNCERTAIN_IMAGE_TYPES]
    if uncertain:
        raise PageDataError(f"readers disagree on whether {uncertain[0]} is a page")
    pages = sorted((n, p) for n, p in entries if isPage(n))
    if not pages:
        raise PageDataError("no page images")
    names = [n for n, _ in pages]
    if len({tuple(naturalKey(n)) for n in names}) != len(names):
        raise PageDataError("page names collide in natural order")
    if sorted(names, key=naturalKey) != names or sorted(names, key=str.lower) != names:
        raise PageDataError("page names sort differently in plain and natural order")
    return pages

def checkPage(el, info: dict) -> bool:
    """Compare an existing <Page> to the image it claims to describe.
    Raises PageDataError on any mismatch; returns True if anything matched.
    """
    matched = False
    for k in INT_ATTRS + STR_ATTRS:
        v = el.get(k)
        if v is None or k not in info:
            continue
        try:
            same = int(v) == int(info[k]) if k in INT_ATTRS else v.strip().lower() == info[k].lower()
        except ValueError:
            same = False
        if not same:
            raise PageDataError(f"page {el.get('Image')} has {k}={v}, image has {info[k]}")
        matched = True
    return matched

def updateComicInfo(xml, entries):
    """Fill in missing page data in a ComicInfo.xml document.
    xml is the existing document as bytes, or None to create one.
    entries is [(arcname, path)] for every file in the archive.
    Existing values are never overwritten. Returns the new document as
    bytes, or None if nothing needed to change. Raises PageDataError if the
    data cannot be guaranteed to land on the right pages.
    """
    root = ET.Element('ComicInfo') if xml is None else ET.fromstring(xml)
    changed = xml is None
    pages = pageOrder(entries)
    infos = [pageInfo(p) for _, p in pages]

    count_el = root.find('PageCount')
    if count_el is not None:
        try:
            count = int((count_el.text or '').strip())
        except ValueError:
            raise PageDataError(f"PageCount is {count_el.text!r}")
        if count != len(pages):
            raise PageDataError(f"PageCount is {count}, archive has {len(pages)} pages")

    pages_el = root.find('Pages')
    by_index = {}
    corroborated = count_el is not None
    for el in [] if pages_el is None else pages_el.findall('Page'):
        try:
            i = int(el.get('Image', ''))
        except ValueError:
            raise PageDataError(f"page entry has Image={el.get('Image')!r}")
        if i in by_index or not 0 <= i < len(pages):
            raise PageDataError(f"page entry Image={i} is duplicated or out of range")
        by_index[i] = el
        corroborated = checkPage(el, infos[i]) or corroborated
    if by_index and not corroborated:
        raise PageDataError("existing page entries cannot be matched to images")

    if pages_el is None:
        pages_el = ET.Element('Pages')
        insertBefore(root, pages_el, AFTER_PAGES)
        changed = True

    if count_el is None:
        count_el = ET.Element('PageCount')
        count_el.text = str(len(pages))
        insertBefore(root, count_el, AFTER_PAGECOUNT)
        changed = True

    for i, info in enumerate(infos):
        el = by_index.get(i)
        if el is None:
            el = ET.SubElement(pages_el, 'Page', {'Image': str(i)})
            changed = True
        for k, v in info.items():
            if el.get(k) is None:
                el.set(k, v)
                changed = True

    if not changed:
        return None
    if hasattr(ET, 'indent'):
        ET.indent(root, space='  ')
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)

def findComicInfo(paths, start):
    """Return the shallowest ComicInfo.xml (case-insensitive) among paths, or None."""
    found = [p for p in paths if os.path.basename(p).lower() == 'comicinfo.xml']
    if not found:
        return None
    return min(found, key=lambda p: (os.path.relpath(p, start=start).count(os.sep), p))


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=f"v{get_version()}", prog_name="cbrXz")
@click.argument('src', type=click.Path(exists=True, dir_okay=True, file_okay=True, path_type=str))
@click.argument('dst', type=click.Path(dir_okay=True, file_okay=True, path_type=str))
@click.option('--root', required=False, type=click.Path(exists=True, dir_okay=True, file_okay=True, path_type=str), help='Override root for relative paths')
@click.option('-F', '--replace', is_flag=True, help='Overwrite existing destination files')
@click.option('-N', '--dry-run', 'dryrun', is_flag=True, help='Plan actions but do not write outputs')
@click.option('--log-level', default='INFO', type=click.Choice(['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET'], case_sensitive=False), help='Logging verbosity')
def main(src, dst, root, replace, dryrun, log_level):
    # cfg = {}
    total = 0
    books = []
    book_count = 0

    # configure logging now that args are known
    log_level = getattr(logging, str(log_level).upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s:%(funcName)s:%(levelname)s - %(message)s'
    )

    source = os.path.abspath(src)
    destination = os.path.abspath(dst)

    # early input validation (no logging)
    if not (os.path.isdir(source) or os.path.isfile(source)):
        raise click.UsageError(f"Source must be a file or directory: {source}")
    if os.path.isfile(destination):
        raise click.UsageError(f"Destination must be a directory (not a file): {destination}")
    try:
        os.makedirs(destination, exist_ok=True)
    except Exception as e:  # pylint: disable=broad-except
        raise click.ClickException(f"Cannot create destination directory: {destination} ({e})")

    logger.debug("source: %s", source)
    logger.debug("destination: %s", destination)

    if os.path.isfile(source) == True:
        # single file mode is a cheat 
        books = [source]
        total = 1
        book_count = 1
    else:
        for path, _, files in os.walk(source):
            for f in files:
                total += 1

                f_ext = os.path.splitext(f)[1].lower()
                logger.debug("f_ext = %s", f_ext)
                if f_ext in BOOK_TYPES:
                    logger.debug("valid type")
                    if filterBook(f):
                        logger.debug("filtered - next pls")
                        continue
                    logger.debug("good book - adding to array")
                    books.append(os.path.join(path, f))
                    book_count += 1
                    logger.debug("books+=1 -> %d collected (of %d files)", book_count, total)
                else:
                    logger.info("%s is not a supported filetype.", os.path.join(path, f))

    if root is not None:
        root_abs = os.path.abspath(root)
        try:
            if os.path.commonpath([source, root_abs]) == root_abs:
                source = root_abs
            else:
                # raise usage error for clean early exit
                raise click.UsageError(f"{source} is not the child of {root_abs}")
        except ValueError:
            # Different drives on Windows can raise ValueError in commonpath
            raise click.UsageError(f"{source} and {root_abs} are on different drives")

    # Determine base for relative paths (handles file vs dir sources)
    rel_base = source if os.path.isdir(source) else os.path.dirname(source)

    logger.info("beginning - %d books of %d files.", book_count, total)
    logger.debug("----")

    # exit()

    books.sort()
    for book in books:
        logger.info("EVENT: processing %s", book)
        logger.debug("            book: %s", book)
        t_book = os.path.relpath(book, start=rel_base)
        logger.debug("          t_book: %s", t_book)
        book_p, book_f = os.path.split(t_book)
        logger.debug("          book_p: %s", book_p)
        logger.debug("          book_f: %s", book_f)
        book_b, book_t = os.path.splitext(book_f)
        logger.debug("          book_b: %s", book_b)
        book_t = book_t.lower()
        logger.debug("          book_t: %s", book_t)
        book_destination = os.path.join(destination, book_p)
        logger.debug("book_destination: %s", book_destination)

        if not os.path.exists(book_destination):
            logger.info("EVENT: making %s", book_destination)
            if not dryrun:
                os.makedirs(book_destination)

        if book_t in ['.cbr', '.rar']:
            book_z = "{}.cbz".format(book_b)
            logger.debug("          book_z: %s", book_z)
            f_book_z = os.path.join(book_destination, book_z)
            logger.debug("        f_book_z: %s", f_book_z)
            if not os.path.isfile(f_book_z) or replace:
                if dryrun:
                    logger.info("EVENT: would extract %s and create %s", book_f, f_book_z)
                    logger.debug("----")
                    continue
                with tempfile.TemporaryDirectory() as tmp_x_dir:
                    logger.debug("       tmp_x_dir: %s", tmp_x_dir)
                    try:
                        with rarfile.RarFile(book) as rar:
                            logger.info("EVENT: extracting %s to %s", book_f, tmp_x_dir)
                            try:
                                rar.extractall(tmp_x_dir)
                            except rarfile.RarWarning as warning:
                                logger.warning("Non-fatal error handling %s - some data loss likely.", book_f)
                                logger.debug("rarfile warning: %s", warning)
                    except rarfile.NotRarFile:
                        logger.warning("Non-fatal error handling %s - actually a Zip.", book_f)
                        logger.info("EVENT: copying %s to %s", book_f, f_book_z)
                        if os.path.isfile(f_book_z):
                            os.unlink(f_book_z)
                        shutil.copy2(book, f_book_z)
                        logger.debug("----")
                        continue
                    except (rarfile.BadRarFile, rarfile.RarCRCError):
                        logger.error("ERROR: corrupted archive: %s", book_f)
                        logger.debug("----")
                        continue

                    # Build the archive next to its final location so publishing it is an
                    # atomic rename instead of a second full-size copy out of a temp dir.
                    t_book_z = "{}.part".format(f_book_z)
                    logger.debug("        t_book_z: %s", t_book_z)
                    try:
                        with zipfile.ZipFile(t_book_z, 'w', compression=zipfile.ZIP_STORED) as zip:
                            pages = []
                            for xt_p, _, xt_fis in os.walk(tmp_x_dir):
                                for xt_fi in xt_fis:
                                    rel = os.path.relpath(os.path.join(xt_p, xt_fi), start=tmp_x_dir)
                                    rel = rel.replace(os.sep, '/')
                                    if filterPage(rel):
                                        continue
                                    # TBD: test for credit pages
                                    pages.append(os.path.join(xt_p, xt_fi))
                            pages.sort()
                            comicinfo = findComicInfo(pages, tmp_x_dir)
                            xml = None
                            if comicinfo is None:
                                logger.debug("no comicinfo.xml found - creating one")
                                comicinfo = os.path.join(tmp_x_dir, 'ComicInfo.xml')
                            else:
                                logger.debug("comicinfo exists.")
                                with open(comicinfo, 'rb') as f:
                                    xml = f.read()
                            entries = [(os.path.relpath(p, start=tmp_x_dir).replace(os.sep, '/'), p) for p in pages]
                            try:
                                xml = updateComicInfo(xml, entries)
                            except ET.ParseError as e:
                                logger.warning("Cannot parse ComicInfo.xml in %s - leaving it unchanged.", book_f)
                                logger.debug("parse error: %s", e)
                                xml = None
                            except PageDataError as e:
                                logger.warning("Not writing page data for %s - %s.", book_f, e)
                                xml = None
                            if xml is not None:
                                logger.info("EVENT: writing page data to %s", os.path.relpath(comicinfo, start=tmp_x_dir))
                                with open(comicinfo, 'wb') as f:
                                    f.write(xml)
                                if comicinfo not in pages:
                                    pages.append(comicinfo)
                                    pages.sort()
                            logger.info("EVENT: making %s ", t_book_z)
                            for page in pages:
                                logger.debug("            page: %s", page)
                                page_f = os.path.relpath(page, start=tmp_x_dir).replace(os.sep, "/")
                                if filterPage(page_f):
                                    continue
                                logger.debug("          page_f: %s", page_f)
                                zip.write(page, page_f)
                        # The central directory is only written on close - publish after it.
                        logger.info("EVENT: copying %s to %s", book_z, book_destination)
                        os.replace(t_book_z, f_book_z)
                    except BaseException:
                        if os.path.isfile(t_book_z):
                            os.unlink(t_book_z)
                        raise
        else:
            # Determine destination filename: rename .zip -> .cbz and .7z -> .cb7
            if book_t == '.zip':
                dest_name = f"{book_b}.cbz"
            elif book_t == '.7z':
                dest_name = f"{book_b}.cb7"
            else:
                dest_name = book_f
            book_destination_f = os.path.join(book_destination, dest_name)
            if not os.path.isfile(book_destination_f) or replace:
                logger.info("EVENT: copying %s to %s", book_f, book_destination_f)
                if not dryrun:
                    if os.path.isfile(book_destination_f):
                        logger.info("EVENT: %s already exists - removing...", book_destination_f)
                        os.unlink(book_destination_f)
                    shutil.copy2(book, book_destination_f)
            logger.debug("----")
            continue
        logger.debug("----")

    logger.info("completed - %d books of %d files.", book_count, total)
    logger.info("exiting - success.")

#####


if __name__ == "__main__":
    main()

