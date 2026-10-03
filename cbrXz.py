#! /usr/bin/python3

import click
import json
import logging
import os
import py7zr
import rarfile
import shutil
import tempfile
import time
import zipfile
import re
import xml.etree.ElementTree as ET
from importlib import metadata as _metadata

from PIL import Image


# moved logging configuration into main; keep module-level logger
logger = logging.getLogger(__name__)

BOOK_TYPES = ['.cbr', '.rar', '.cbz', '.zip', '.cb7', '.7z', '.pdf', '.epub']
# Books extracted and repacked as .cbz
REPACK_TYPES = ['.cbr', '.rar', '.cb7', '.7z']
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
STR_ATTRS = ['ImageFormat', 'ImageDpi']


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

def fileEntry(arcname: str, path: str) -> tuple:
    """Describe a file on disk as an archive entry: (arcname, size, opener)."""
    return (arcname, os.path.getsize(path), lambda: open(path, 'rb'))

def zipEntry(zf: zipfile.ZipFile, info: zipfile.ZipInfo) -> tuple:
    """Describe a member of an open zip as an archive entry: (arcname, size, opener)."""
    return (info.filename, info.file_size, lambda: zf.open(info))

def pageInfo(entry: tuple) -> dict:
    """Return ComicInfo <Page> attributes describing the image in entry.
    Only the image header is read.
    ImageSize/ImageWidth/ImageHeight/DoublePage are ComicInfo schema attributes;
    ImageFormat/ImageBitDepth/ImageDpi are extensions.
    """
    name, size, opener = entry
    info = {'ImageSize': str(size)}
    try:
        with opener() as f, Image.open(f) as im:
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
        raise PageDataError(f"cannot read image {name}: {e}") from e
    return info

def naturalKey(s: str) -> list:
    """Sort key matching how comic readers order page names (case-insensitive, numbers by value)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r'(\d+)', s)]

def pageOrder(entries) -> list:
    """Return the page images among entries [(arcname, size, opener)] in reading order.
    Raises PageDataError unless every common ordering (plain, case-insensitive,
    natural) agrees, so a page index means the same image in any reader.
    """
    uncertain = [e[0] for e in entries if os.path.splitext(e[0])[1].lower() in UNCERTAIN_IMAGE_TYPES]
    if uncertain:
        raise PageDataError(f"readers disagree on whether {uncertain[0]} is a page")
    pages = sorted((e for e in entries if isPage(e[0])), key=lambda e: e[0])
    if not pages:
        raise PageDataError("no page images")
    names = [e[0] for e in pages]
    if len(set(names)) != len(names):
        raise PageDataError("archive has duplicate page names")
    if len({tuple(naturalKey(n)) for n in names}) != len(names):
        raise PageDataError("page names collide in natural order")
    if sorted(names, key=naturalKey) != names or sorted(names, key=str.lower) != names:
        raise PageDataError("page names sort differently in plain and natural order")
    return pages

def checkPage(el, info: dict) -> tuple:
    """Compare an existing <Page> to the image it claims to describe.
    Returns (matched, stale): whether any attribute agreed with the image, and
    the attributes that disagree with it.
    """
    matched, stale = False, []
    for k in INT_ATTRS + STR_ATTRS:
        v = el.get(k)
        if v is None or k not in info:
            continue
        try:
            same = int(v) == int(info[k]) if k in INT_ATTRS else v.strip().lower() == info[k].lower()
        except ValueError:
            same = False
        if same:
            matched = True
        else:
            stale.append(k)
    return matched, stale

def updateComicInfo(xml, entries, book_f: str = None):
    """Fill in missing page data in a ComicInfo.xml document.
    xml is the existing document as bytes, or None to create one.
    entries is [(arcname, size, opener)] for every file in the archive.
    book_f names the book in log messages.
    Existing values are kept, except image attributes that contradict their
    image when the existing <Page> entries cover every page (e.g. pages resized
    after ComicInfo.xml was written); those are corrected. Returns the new
    document as bytes, or None if nothing needed to change. Raises
    PageDataError if the data cannot be guaranteed to land on the right pages.
    """
    root = ET.Element('ComicInfo') if xml is None else ET.fromstring(xml)
    changed = xml is None
    pages = pageOrder(entries)
    infos = [pageInfo(e) for e in pages]

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
    stale = {}
    corroborated = count_el is not None
    for el in [] if pages_el is None else pages_el.findall('Page'):
        try:
            i = int(el.get('Image', ''))
        except ValueError:
            raise PageDataError(f"page entry has Image={el.get('Image')!r}")
        if i in by_index or not 0 <= i < len(pages):
            raise PageDataError(f"page entry Image={i} is duplicated or out of range")
        by_index[i] = el
        matched, bad = checkPage(el, infos[i])
        corroborated = matched or corroborated
        if bad:
            stale[i] = bad
    if by_index and not corroborated:
        raise PageDataError("existing page entries cannot be matched to images")
    if stale and len(by_index) != len(pages):
        i, bad = next(iter(stale.items()))
        raise PageDataError(f"page {i} has {bad[0]}={by_index[i].get(bad[0])}, image has {infos[i][bad[0]]}")
    for i, bad in stale.items():
        el, info = by_index[i], infos[i]
        logger.info("EVENT: correcting page %d of %s: %s", i, book_f or 'ComicInfo.xml',
                    ", ".join(f"{k} {el.get(k)} -> {info[k]}" for k in bad))
        for k in bad:
            el.set(k, info[k])
        if 'ImageWidth' in bad or 'ImageHeight' in bad:
            if 'DoublePage' in info:
                el.set('DoublePage', info['DoublePage'])
            elif 'DoublePage' in el.attrib:
                del el.attrib['DoublePage']
        changed = True

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

def zipPageData(path: str, book_f: str) -> tuple:
    """Work out the page data a zip book needs.
    Returns (xml, name): the new ComicInfo.xml bytes (None if nothing should be
    written) and the name of the archive's existing ComicInfo.xml (None if it has none).
    Raises zipfile.BadZipFile if the book cannot be read as a zip.
    """
    try:
        with zipfile.ZipFile(path) as zf:
            infos = [i for i in zf.infolist() if not i.is_dir() and not filterPage(i.filename)]
            found = [i.filename for i in infos if os.path.basename(i.filename).lower() == 'comicinfo.xml']
            name = min(found, key=lambda n: (n.count('/'), n)) if found else None
            existing = zf.read(name) if name else None
            return updateComicInfo(existing, [zipEntry(zf, i) for i in infos], book_f), name
    except ET.ParseError as e:
        logger.warning("Cannot parse ComicInfo.xml in %s - leaving it unchanged.", book_f)
        logger.debug("parse error: %s", e)
    except PageDataError as e:
        logger.warning("Not writing page data for %s - %s.", book_f, e)
    except (RuntimeError, NotImplementedError) as e:
        # an encrypted ComicInfo.xml, or one zipfile cannot decompress
        logger.warning("Cannot read ComicInfo.xml in %s - leaving it unchanged.", book_f)
        logger.debug("read error: %s", e)
    return None, None

def patchZip(path: str, name, data: bytes, before=None) -> None:
    """Give the zip at path a ComicInfo.xml holding data, without rewriting it.
    name is the existing ComicInfo.xml entry to replace, or None to add one.
    The new entry (stored) is written over the old central directory, followed
    by a new central directory, so the other entries are not touched and the
    cost is a few KB whatever the size of the book. A replaced entry's data
    stays in the file, unreferenced. before(start, tail), if given, is called
    with the offset of the old central directory and the bytes from there to
    the end of the file - everything the patch overwrites - before anything is
    written.
    """
    with zipfile.ZipFile(path, 'a') as zf:
        if before is not None:
            zf.fp.seek(zf.start_dir)
            before(zf.start_dir, zf.fp.read())
        if name is None:
            info = zipfile.ZipInfo('ComicInfo.xml', time.localtime()[:6])
        else:
            old = zf.getinfo(name)
            zf.filelist = [i for i in zf.filelist if i.filename != name]
            del zf.NameToInfo[name]
            info = zipfile.ZipInfo(name, old.date_time)
            info.external_attr = old.external_attr
            info.create_system = old.create_system
        info.compress_type = zipfile.ZIP_STORED
        zf.writestr(info, data)

def copyZipBook(src: str, dst: str, book_f: str) -> None:
    """Copy a zip book to dst so it finishes with a ComicInfo.xml holding page data.
    The copy is patched (see patchZip), so its entries are never rewritten. When
    no correct page data can be written the book is copied byte-for-byte. Built
    next to dst and renamed into place so a partial file is never published.
    """
    try:
        xml, name = zipPageData(src, book_f)
    except zipfile.BadZipFile:
        logger.warning("Not writing page data for %s - not a valid zip.", book_f)
        xml, name = None, None
    t_dst = "{}.part".format(dst)
    try:
        shutil.copy2(src, t_dst)
        if xml is not None:
            logger.info("EVENT: writing page data to %s in %s", name or 'ComicInfo.xml', book_f)
            try:
                patchZip(t_dst, name, xml)
            except Exception as e:  # pylint: disable=broad-except
                logger.warning("Not writing page data for %s - cannot patch archive.", book_f)
                logger.debug("patch error: %s", e)
                shutil.copy2(src, t_dst)
            shutil.copystat(src, t_dst)
        os.replace(t_dst, dst)
    except BaseException:
        if os.path.isfile(t_dst):
            os.unlink(t_dst)
        raise

def extractBook(book: str, book_t: str, out_dir: str, book_f: str) -> str:
    """Extract a RAR or 7z book into out_dir.
    Returns 'ok' when extracted, 'zip' when the book is really a zip, 'keep' when
    it cannot be extracted but should still be copied unchanged (encrypted,
    unsupported compression, not a 7z at all), or 'bad' when it is corrupt.
    """
    if book_t in ['.cb7', '.7z']:
        try:
            with py7zr.SevenZipFile(book) as sz:
                if sz.needs_password():
                    logger.warning("Non-fatal error handling %s - encrypted, keeping it as 7z.", book_f)
                    return 'keep'
                logger.info("EVENT: extracting %s to %s", book_f, out_dir)
                sz.extractall(out_dir)
        except py7zr.exceptions.PasswordRequired:
            logger.warning("Non-fatal error handling %s - encrypted, keeping it as 7z.", book_f)
            return 'keep'
        except py7zr.exceptions.UnsupportedCompressionMethodError as e:
            logger.warning("Non-fatal error handling %s - unsupported compression, keeping it as 7z.", book_f)
            logger.debug("py7zr error: %s", e)
            return 'keep'
        except py7zr.exceptions.Bad7zFile:
            if zipfile.is_zipfile(book):
                logger.warning("Non-fatal error handling %s - actually a Zip.", book_f)
                return 'zip'
            logger.warning("Non-fatal error handling %s - not a 7z archive, copying it unchanged.", book_f)
            return 'keep'
        except (py7zr.exceptions.ArchiveError, py7zr.exceptions.CrcError,
                py7zr.exceptions.DecompressionError, py7zr.exceptions.AbsolutePathError) as e:
            logger.error("ERROR: corrupted archive: %s", book_f)
            logger.debug("py7zr error: %s", e)
            return 'bad'
        return 'ok'
    try:
        with rarfile.RarFile(book) as rar:
            logger.info("EVENT: extracting %s to %s", book_f, out_dir)
            try:
                rar.extractall(out_dir)
            except rarfile.RarWarning as warning:
                logger.warning("Non-fatal error handling %s - some data loss likely.", book_f)
                logger.debug("rarfile warning: %s", warning)
    except rarfile.NotRarFile:
        logger.warning("Non-fatal error handling %s - actually a Zip.", book_f)
        return 'zip'
    except (rarfile.BadRarFile, rarfile.RarCRCError):
        logger.error("ERROR: corrupted archive: %s", book_f)
        return 'bad'
    return 'ok'

def findComicInfo(paths, start):
    """Return the shallowest ComicInfo.xml (case-insensitive) among paths, or None."""
    found = [p for p in paths if os.path.basename(p).lower() == 'comicinfo.xml']
    if not found:
        return None
    return min(found, key=lambda p: (os.path.relpath(p, start=start).count(os.sep), p))

def packBook(tmp_x_dir: str, f_book_z: str, book_f: str) -> None:
    """Pack the book extracted into tmp_x_dir as the .cbz f_book_z, with page data in its ComicInfo.xml."""
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
            entries = [fileEntry(os.path.relpath(p, start=tmp_x_dir).replace(os.sep, '/'), p) for p in pages]
            try:
                xml = updateComicInfo(xml, entries, book_f)
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
        logger.info("EVENT: publishing %s", f_book_z)
        os.replace(t_book_z, f_book_z)
    except BaseException:
        if os.path.isfile(t_book_z):
            os.unlink(t_book_z)
        raise


class JournalError(Exception):
    """The journal cannot undo an interrupted patch - the run must stop."""

def restoreTail(path: str, start: int, tail: bytes, atime_ns: int, mtime_ns: int) -> None:
    """Undo a patch: put back the bytes from start on and drop anything after them."""
    with open(path, 'r+b') as f:
        f.seek(start)
        f.write(tail)
        f.truncate()
        f.flush()
        os.fsync(f.fileno())
    os.utime(path, ns=(atime_ns, mtime_ns))

class Journal:
    """What an in-place run has finished, so a rerun skips those books unopened.
    One JSON object per line. {"book": rel, "size", "mtime_ns", "outcome"} marks
    a book done, and it is skipped while its size and mtime are unchanged. rel is
    relative to the tree root with forward slashes, so the journal stays valid
    when the tree is mounted elsewhere (e.g. a share and the NAS behind it).
    {"patch": path, ...} is written just before a book is patched in place, once
    the bytes the patch overwrites are saved beside the journal; if a run stops
    before the next record, the next run puts them back.
    """
    def __init__(self, path: str, dryrun: bool):
        self.path = path
        self.tail_path = path + '.tail'
        self.done = {}
        self.f = None
        pending = None
        if os.path.isfile(path):
            with open(path, encoding='utf-8') as f:
                for line in f:
                    try:
                        rec = json.loads(line)
                    except ValueError:
                        continue  # a line cut short by a crash
                    # books are processed one at a time, so any record settles the patch before it
                    pending = rec if 'patch' in rec else None
                    if 'book' in rec:
                        self.done[rec['book']] = (rec['size'], rec['mtime_ns'])
        if dryrun:
            if pending is not None:
                logger.warning("Would undo the interrupted patch of %s", pending['patch'])
            return
        if pending is not None:
            self.undo(pending)
        elif os.path.isfile(self.tail_path):
            os.unlink(self.tail_path)
        self.f = open(path, 'ab')
        if self.f.tell():
            with open(path, 'rb') as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b'\n':
                    self.f.write(b'\n')  # end a line cut short by a crash

    def undo(self, rec: dict) -> None:
        """Put back what an interrupted patch overwrote."""
        if not os.path.isfile(rec['patch']):
            # a .zip renamed to .cbz once patched - the patch finished
            logger.info("%s has moved since it was patched - nothing to undo", rec['patch'])
            if os.path.isfile(self.tail_path):
                os.unlink(self.tail_path)
            return
        try:
            with open(self.tail_path, 'rb') as f:
                tail = f.read()
        except OSError:
            tail = None
        if tail is None or len(tail) != rec['tail']:
            raise JournalError("cannot undo the interrupted patch of {}: {} is missing or damaged".format(
                rec['patch'], self.tail_path))
        logger.warning("EVENT: undoing the interrupted patch of %s", rec['patch'])
        restoreTail(rec['patch'], rec['offset'], tail, rec['atime_ns'], rec['mtime_ns'])
        os.unlink(self.tail_path)

    def write(self, rec: dict) -> None:
        if self.f is None:
            return
        self.f.write(json.dumps(rec).encode('utf-8') + b'\n')
        self.f.flush()
        os.fsync(self.f.fileno())

    def isDone(self, rel: str, path: str) -> bool:
        """Return True if the book at path was finished and has not changed since."""
        if rel not in self.done:
            return False
        st = os.stat(path)
        return self.done[rel] == (st.st_size, st.st_mtime_ns)

    def record(self, rel: str, path: str, outcome: str) -> None:
        """Mark the book now at path finished."""
        if self.f is None:
            return
        st = os.stat(path)
        self.write({'book': rel, 'size': st.st_size, 'mtime_ns': st.st_mtime_ns, 'outcome': outcome})
        self.done[rel] = (st.st_size, st.st_mtime_ns)
        if os.path.isfile(self.tail_path):
            os.unlink(self.tail_path)  # the patch it saved is settled

    def beginPatch(self, path: str, start: int, tail: bytes, st) -> None:
        """Durably save what a patch of path is about to overwrite."""
        if self.f is None:
            return
        with open(self.tail_path, 'wb') as f:
            f.write(tail)
            f.flush()
            os.fsync(f.fileno())
        self.write({'patch': path, 'offset': start, 'tail': len(tail),
                    'atime_ns': st.st_atime_ns, 'mtime_ns': st.st_mtime_ns})

    def close(self) -> None:
        if self.f is not None:
            self.f.close()
            self.f = None

def patchInPlace(book: str, name, xml: bytes, journal, book_f: str) -> None:
    """Patch page data into the zip book where it lies (see patchZip), keeping its mtime.
    What the patch overwrites is kept in the journal until the book is recorded,
    so a crash is undone by the next run, and in memory, so a patch that fails
    is undone at once.
    """
    st = os.stat(book)
    saved = []
    def before(start, tail):
        saved.append((start, tail))
        if journal is not None:
            journal.beginPatch(book, start, tail, st)
    logger.info("EVENT: writing page data to %s in %s", name or 'ComicInfo.xml', book_f)
    try:
        patchZip(book, name, xml, before)
        with open(book, 'rb+') as f:
            os.fsync(f.fileno())
        os.utime(book, ns=(st.st_atime_ns, st.st_mtime_ns))
    except BaseException:
        if saved:
            logger.warning("EVENT: undoing the failed patch of %s", book_f)
            restoreTail(book, saved[0][0], saved[0][1], st.st_atime_ns, st.st_mtime_ns)
            if journal is not None:
                journal.write({'undone': book})
        raise

def sniffArchive(book: str):
    """Return the archive type book really is ('.cbz', '.cbr' or '.cb7'), whatever its name, or None."""
    try:
        if rarfile.is_rarfile(book):
            return '.cbr'
        if py7zr.is_7zfile(book):
            return '.cb7'
        if zipfile.is_zipfile(book):
            return '.cbz'
    except OSError:
        pass
    return None

def trashBook(book: str, trash_dir: str, book_f: str, dryrun: bool) -> str:
    """Move an unreadable book into trash_dir, never overwriting what is already there."""
    base, ext = os.path.splitext(os.path.join(trash_dir, os.path.basename(book)))
    target, n = base + ext, 1
    while os.path.exists(target):
        target, n = "{} ({}){}".format(base, n, ext), n + 1
    logger.warning("Moving unreadable %s to %s", book_f, target)
    if not dryrun:
        os.makedirs(trash_dir, exist_ok=True)
        shutil.move(book, target)
    return 'trashed'

def claimTarget(book: str, target: str, book_f: str, replace: bool) -> bool:
    """Return True if book may be written to target, its new name in the tree."""
    if os.path.normcase(book) == os.path.normcase(target) or not os.path.exists(target):
        return True
    if replace:
        logger.info("EVENT: %s already exists - replacing...", target)
        return True
    logger.warning("Leaving %s alone - %s already exists (use --replace to overwrite).", book_f, target)
    return False

def inPlaceBook(book: str, book_t: str, trash_dir: str, replace: bool, dryrun: bool, journal=None) -> tuple:
    """Process book where it lies: it finishes as a .cbz with page data, and an
    unreadable book is moved to trash_dir. Returns (outcome, path): what
    happened - 'current', 'updated', 'converted', 'trashed', 'kept' or
    'skipped' - and where the book now is (None if it left the tree or should
    be looked at again by the next run).
    """
    book_d, book_f = os.path.split(book)
    if book_t not in ['.cbz', '.zip'] + REPACK_TYPES:
        return 'current', book
    real_t = sniffArchive(book)
    if real_t is None:
        return trashBook(book, trash_dir, book_f, dryrun), None
    f_book_z = os.path.join(book_d, os.path.splitext(book_f)[0] + '.cbz')

    if real_t == '.cbz':
        try:
            xml, name = zipPageData(book, book_f)
        except zipfile.BadZipFile:
            return trashBook(book, trash_dir, book_f, dryrun), None
        renamed = os.path.normcase(book) != os.path.normcase(f_book_z)
        if xml is None and not renamed:
            return 'current', book
        if not claimTarget(book, f_book_z, book_f, replace):
            return 'skipped', None
        if dryrun:
            logger.info("EVENT: would update %s as %s", book_f, f_book_z)
            return 'updated', None
        if xml is not None:
            patchInPlace(book, name, xml, journal, book_f)
        if renamed:
            logger.info("EVENT: renaming %s to %s", book_f, f_book_z)
            os.replace(book, f_book_z)
        return 'updated', f_book_z

    if not claimTarget(book, f_book_z, book_f, replace):
        return 'skipped', None
    if dryrun:
        logger.info("EVENT: would extract %s and replace it with %s", book_f, f_book_z)
        return 'converted', None
    with tempfile.TemporaryDirectory() as tmp_x_dir:
        status = extractBook(book, real_t, tmp_x_dir, book_f)
        if status == 'bad':
            return trashBook(book, trash_dir, book_f, dryrun), None
        if status == 'keep':
            # encrypted or unsupported compression - readable by other tools, so left as it is
            return 'kept', book
        if status == 'zip':
            return inPlaceBook(book, '.cbz', trash_dir, replace, dryrun, journal)
        packBook(tmp_x_dir, f_book_z, book_f)
    os.unlink(book)
    return 'converted', f_book_z

@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=f"v{get_version()}", prog_name="cbrXz")
@click.argument('src', type=click.Path(exists=True, dir_okay=True, file_okay=True, path_type=str))
@click.argument('dst', required=False, type=click.Path(dir_okay=True, file_okay=True, path_type=str))
@click.option('--root', required=False, type=click.Path(exists=True, dir_okay=True, file_okay=True, path_type=str), help='Override root for relative paths')
@click.option('-F', '--replace', is_flag=True, help='Overwrite existing destination files')
@click.option('-N', '--dry-run', 'dryrun', is_flag=True, help='Plan actions but do not write outputs')
@click.option('-i', '--in-place', 'in_place', is_flag=True, help='Process SRC where it lies instead of writing to DST')
@click.option('--trash', required=False, type=click.Path(file_okay=False, path_type=str), help='Where --in-place moves unreadable books (default: SRC/_trash)')
@click.option('--journal', 'journal_path', required=False, type=click.Path(dir_okay=False, path_type=str), help='Record of books --in-place has finished, so a rerun skips them (default: SRC/_cbrXz_journal.jsonl)')
@click.option('--log-level', default='INFO', type=click.Choice(['CRITICAL','ERROR','WARNING','INFO','DEBUG','NOTSET'], case_sensitive=False), help='Logging verbosity')
def main(src, dst, root, replace, dryrun, in_place, trash, journal_path, log_level):
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

    # early input validation (no logging)
    if not (os.path.isdir(source) or os.path.isfile(source)):
        raise click.UsageError(f"Source must be a file or directory: {source}")
    if in_place:
        if dst is not None:
            raise click.UsageError("DST cannot be given with --in-place")
        destination = None
    else:
        if dst is None:
            raise click.UsageError("Missing argument 'DST' (or use --in-place)")
        if trash is not None or journal_path is not None:
            raise click.UsageError("--trash and --journal are only used with --in-place")
        destination = os.path.abspath(dst)
        if os.path.isfile(destination):
            raise click.UsageError(f"Destination must be a directory (not a file): {destination}")
        try:
            os.makedirs(destination, exist_ok=True)
        except Exception as e:  # pylint: disable=broad-except
            raise click.ClickException(f"Cannot create destination directory: {destination} ({e})")
    if in_place:
        tree = source if os.path.isdir(source) else os.path.dirname(source)
        trash = os.path.abspath(trash or os.path.join(tree, '_trash'))
        journal_path = os.path.abspath(journal_path or os.path.join(tree, '_cbrXz_journal.jsonl'))

    logger.debug("source: %s", source)
    logger.debug("destination: %s", destination)

    if os.path.isfile(source) == True:
        # single file mode is a cheat 
        books = [source]
        total = 1
        book_count = 1
    else:
        for path, dirs, files in os.walk(source):
            # never pick up books already moved to the trash
            dirs[:] = [d for d in dirs if trash is None or os.path.normcase(os.path.join(path, d)) != os.path.normcase(trash)]
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
    outcomes = {}
    journal = None
    if in_place:
        try:
            journal = Journal(journal_path, dryrun)
        except JournalError as e:
            raise click.ClickException(str(e))
        logger.info("journal: %s (%d books recorded)", journal_path, len(journal.done))
    for book in books:
        if in_place:
            rel = os.path.relpath(book, start=rel_base).replace(os.sep, '/')
            if journal.isDone(rel, book):
                logger.debug("unchanged since recorded - skipping %s", book)
                outcomes['journaled'] = outcomes.get('journaled', 0) + 1
                continue
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
        if in_place:
            try:
                outcome, now = inPlaceBook(book, book_t, os.path.join(trash, book_p), replace, dryrun, journal)
                if now is not None and not dryrun:
                    journal.record(os.path.relpath(now, start=rel_base).replace(os.sep, '/'), now, outcome)
            except JournalError:
                raise
            except Exception as e:  # pylint: disable=broad-except
                # one bad book must not end a run over the whole collection
                logger.error("ERROR: cannot process %s - %s", book, e)
                logger.debug("error", exc_info=True)
                outcome = 'failed'
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            logger.debug("----")
            continue
        book_destination = os.path.join(destination, book_p)
        logger.debug("book_destination: %s", book_destination)

        if not os.path.exists(book_destination):
            logger.info("EVENT: making %s", book_destination)
            if not dryrun:
                os.makedirs(book_destination)

        if book_t in REPACK_TYPES:
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
                    status = extractBook(book, book_t, tmp_x_dir, book_f)
                    if status == 'zip':
                        logger.info("EVENT: copying %s to %s", book_f, f_book_z)
                        copyZipBook(book, f_book_z, book_f)
                    elif status == 'keep':
                        f_book_7 = os.path.join(book_destination, "{}.cb7".format(book_b))
                        logger.info("EVENT: copying %s to %s", book_f, f_book_7)
                        if os.path.isfile(f_book_7):
                            os.unlink(f_book_7)
                        shutil.copy2(book, f_book_7)
                    if status != 'ok':
                        logger.debug("----")
                        continue

                    packBook(tmp_x_dir, f_book_z, book_f)
        else:
            # Determine destination filename: rename .zip -> .cbz
            if book_t == '.zip':
                dest_name = f"{book_b}.cbz"
            else:
                dest_name = book_f
            book_destination_f = os.path.join(book_destination, dest_name)
            if not os.path.isfile(book_destination_f) or replace:
                logger.info("EVENT: copying %s to %s", book_f, book_destination_f)
                if not dryrun:
                    if os.path.isfile(book_destination_f):
                        logger.info("EVENT: %s already exists - replacing...", book_destination_f)
                    if book_t in ['.cbz', '.zip']:
                        copyZipBook(book, book_destination_f, book_f)
                    else:
                        if os.path.isfile(book_destination_f):
                            os.unlink(book_destination_f)
                        shutil.copy2(book, book_destination_f)
            logger.debug("----")
            continue
        logger.debug("----")

    logger.info("completed - %d books of %d files.", book_count, total)
    if in_place:
        journal.close()
        logger.info("in place: %s", ", ".join(f"{n} {k}" for k, n in sorted(outcomes.items())) or "nothing to do")
        if outcomes.get('failed'):
            logger.error("%d books could not be processed - see the errors above.", outcomes['failed'])
            raise SystemExit(1)
    logger.info("exiting - success.")

#####


if __name__ == "__main__":
    main()

