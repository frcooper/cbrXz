#! /usr/bin/python3

import click
import inspect
import logging
import os
import rarfile
import shutil
import tempfile
import zipfile
import re
from importlib import metadata as _metadata



# moved logging configuration into main; keep module-level logger
logger = logging.getLogger(__name__)

BOOK_TYPES = ['.cbr', '.rar', '.cbz', '.zip', '.cb7', '.7z', '.pdf', '.epub']

def get_version() -> str:
    """Return the project version, preferring installed package metadata.
    Fallback to reading pyproject.toml's [project].version when running from source.
    """
    pkg_name = "cbrXz"
    try:
        v = _metadata.version(pkg_name)
        return v
    except Exception:
        pass
    # Fallback: read pyproject.toml next to this file or repo root
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "pyproject.toml"),
        os.path.join(os.path.abspath(os.getcwd()), "pyproject.toml"),
    ]
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            # Simple regex for: version = "x.y.z"
            m = re.search(r"^version\s*=\s*\"([^\"]+)\"", content, re.MULTILINE)
            if m:
                return m.group(1)
        except Exception:
            continue
    return "0.0.0"

def isZip(file_path):
    # Define the magic number for ZIP files
    zip_magic_number = b'\x50\x4b\x03\x04'  # PK\x03\x04

    # Read the first 4 bytes of the file
    with open(file_path, 'rb') as f:
        file_header = f.read(4)

    # Check if the file header matches the ZIP magic number
    return file_header == zip_magic_number

def filterBook(s):
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


def debug(s):
    print("{}[{}]->{}: {}".format(inspect.stack()[2].function, inspect.stack()[2].lineno, inspect.stack()[1].function, s))


def error(s):
    print("{}[{}] FATAL ERROR: {}".format(inspect.stack()[2].function, inspect.stack()[2].lineno, s))


def log(s):
    print("{}".format(s))


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
        for path, folders, files in os.walk(source):                                                  # pylint: disable=W0612
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
                    logger.debug("books[] = %s", books)
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
                            except rarfile.RarCRCError:
                                logger.error("ERROR: corrupted archive: %s", book_f)
                                logger.debug("----")
                                continue
                            except rarfile.BadRarFile:
                                logger.error("ERROR: corrupted archive: %s", book_f)
                                logger.debug("----")
                                continue
                    except rarfile.NotRarFile:
                        logger.warning("Non-fatal error handling %s - actually a Zip.", book_f)
                        if not os.path.isfile(f_book_z) or replace:
                            logger.info("EVENT: copying %s to %s", book_f, f_book_z)
                            if not dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copy2(book, f_book_z)
                        logger.debug("----")
                        continue
                    except rarfile.RarCRCError:
                        logger.error("ERROR: corrupted archive: %s", book_f)
                        logger.debug("----")
                        continue
                    except rarfile.BadRarFile:
                        logger.error("ERROR: corrupted archive: %s", book_f)
                        logger.debug("----")
                        continue
                    with tempfile.TemporaryDirectory() as tmp_b_dir:
                        logger.debug("       tmp_b_dir: %s", tmp_b_dir)
                        t_book_z = os.path.join(tmp_b_dir, book_z)
                        logger.debug("        t_book_z: %s", t_book_z)
                        with zipfile.ZipFile(t_book_z, 'w') as zip:
                            hasComicInfoXml = False
                            pages = []
                            for xt_p, xt_fls, xt_fis in os.walk(tmp_x_dir):                                              # pylint: disable=W0612
                                for xt_fi in xt_fis:
                                    rel = os.path.relpath(os.path.join(xt_p, xt_fi), start=tmp_x_dir)
                                    rel = rel.replace(os.sep, '/')
                                    if filterPage(rel):
                                        continue
                                    # TBD: test for credit pages, comicinfo.xml
                                    if xt_fi in ['ComicInfo.xml']:
                                        hasComicInfoXml = True
                                        logger.debug("comicinfo exists.")
                                    pages.append(os.path.join(xt_p, xt_fi))
                            if not hasComicInfoXml:
                                logger.debug("no comicinfo.xml found - injecting skeleton(?)")
                            pages.sort()
                            logger.info("EVENT: making %s ", t_book_z)
                            for page in pages:
                                logger.debug("            page: %s", page)
                                page_f = os.path.relpath(page, start=tmp_x_dir).replace(os.sep, "/")
                                if filterPage(page_f):
                                    continue
                                logger.debug("          page_f: %s", page_f)
                                zip.write(page, page_f)
                            zip.close()
                            logger.info("EVENT: copying %s to %s", book_z, book_destination)
                            if not dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copy2(t_book_z, f_book_z)
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
                        # os.unlink(book_destination_f)
                        pass
                    shutil.copy2(book, book_destination_f)
            logger.debug("----")
            continue
        logger.debug("----")

    logger.info("completed - %d books of %d files.", book_count, total)
    logger.info("exiting - success.")

#####


if __name__ == "__main__":
    main()

