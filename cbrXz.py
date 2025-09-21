#! /usr/bin/python3

import argparse
import inspect
import logging
import os
import rarfile
import shutil
import tempfile
import zipfile



logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s:%(funcName)s:%(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

BOOK_TYPES = ['.cbr', '.rar', '.cbz', '.zip', '.cb7', '.7z', '.pdf', '.epub']

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

def filterPage(s):
    return False


def debug(s):
    print("{}[{}]->{}: {}".format(inspect.stack()[2].function, inspect.stack()[2].lineno, inspect.stack()[1].function, s))


def error(s):
    print("{}[{}] FATAL ERROR: {}".format(inspect.stack()[2].function, inspect.stack()[2].lineno, s))


def log(s):
    print("{}".format(s))


def main():
    # cfg = {}
    total = 0
    books = []
    book_count = 0

    parser = argparse.ArgumentParser()
    parser.add_argument('src')
    parser.add_argument('dst')
    parser.add_argument('--root', required=False)
    parser.add_argument('-R', '--rar-only', dest='raronly', required=False, action='store_true')
    parser.add_argument('-F', '--replace', dest='replace', required=False, action='store_true')
    parser.add_argument('-N', '--dry-run', dest='dryrun', required=False, action='store_true')
    args = parser.parse_args()

    source = os.path.abspath(args.src)

    destination = os.path.abspath(args.dst)

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
                    if args.raronly:
                        logger.debug("raronly active")
                        if not f_ext in ['.cbr', '.rar']:
                            logger.debug("not a rar - next pls")
                            continue
                    if filterBook(f):
                        logger.debug("filtered - next pls")
                        continue
                    logger.debug("good book - adding to array")
                    books.append(os.path.join(path, f))
                    book_count += 1
                    logger.debug("books[] = %s", books)
                else:
                    logger.info("%s is not a supported filetype.", os.path.join(path, f))

    if args.root is not None:
        root = os.path.abspath(args.root)
        try:
            if os.path.commonpath([source, root]) == root:
                source = root
            else:
                logger.error("ERROR: %s is not the child of %s", source, root)
                exit()
        except ValueError:
            # Different drives on Windows can raise ValueError in commonpath
            logger.error("ERROR: %s and %s are on different drives", source, root)
            exit()

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
            if not args.dryrun:
                os.makedirs(book_destination)

        if not book_t in ['.cbr', '.rar']:
            book_destination_f = os.path.join(book_destination, book_f)
            if not os.path.isfile(book_destination_f) or args.replace:
                logger.info("EVENT: copying %s to %s", book_f, book_destination)
                if not args.dryrun:
                    if os.path.isfile(book_destination_f):
                        logger.info("EVENT: %s already exists - removing...", book_destination_f)
                        # os.unlink(book_destination_f)
                        pass
                    shutil.copyfile(book, book_destination_f)
            logger.debug("----")
            continue

        if book_t in ['.cbr', '.rar']:
            book_z = "{}.cbz".format(book_b)
            logger.debug("          book_z: %s", book_z)
            f_book_z = os.path.join(book_destination, book_z)
            logger.debug("        f_book_z: %s", f_book_z)
            if not os.path.isfile(os.path.join(book_destination, book_z)) or args.replace:
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
                        if not os.path.isfile(f_book_z) or args.replace:
                            logger.info("EVENT: copying %s to %s", book_f, f_book_z)
                            if not args.dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copyfile(book, f_book_z)
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
                                logger.debug("          page_f: %s", page_f)
                                zip.write(page, page_f)
                            zip.close()
                            logger.info("EVENT: copying %s to %s", book_z, book_destination)
                            if not args.dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copyfile(t_book_z, f_book_z)
        logger.debug("----")

    logger.info("completed - %d books of %d files.", book_count, total)
    logger.info("exiting - success.")

#####


if __name__ == "__main__":
    main()

