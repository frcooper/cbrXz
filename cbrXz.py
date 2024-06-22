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
    return True

def filterPage(s):
    return True


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

    logger.debug("source: {}".format(source))
    logger.debug("destination: {}".format(destination))

    if os.path.isfile(source) == True:
        # single file mode is a cheat 
        books = [source]
        total = 1
        book_count = 1
    else:
        for path, folders, files in os.walk(source):                                                  # pylint: disable=W0612
            for f in files:
                total += 1

                f_ext = os.path.splitext(f)[1]
                if f_ext in BOOK_TYPES:
                    if args.raronly:
                        if not f_ext in ['.cbr', '.rar']:
                            continue
                    if filterBook(f):
                        continue
                    books.append(os.path.join(path, f))
                    book_count += 1
                else:
                    logger.warning("{} is not a supported filetype.".format(os.path.join(path, f)))

    if args.root is not None:
        root = os.path.abspath(args.root)
        if source.startswith(root):
            source = root
        else:
            logger.error("ERROR: {} is not the child of {}".format(source, root))
            exit()

    logger.info("beginning - {} books of {} files.".format(book_count, total))
    logger.debug("----")

    # exit()

    books.sort()
    for book in books:
        logger.info("EVENT: processing {}".format(book))
        logger.debug("            book: {}".format(book))
        t_book = book[len(source) + 1:]
        logger.debug("          t_book: {}".format(t_book))
        book_p, book_f = os.path.split(t_book)
        logger.debug("          book_p: {}".format(book_p))
        logger.debug("          book_f: {}".format(book_f))
        book_b, book_t = os.path.splitext(book_f)
        logger.debug("          book_b: {}".format(book_b))
        logger.debug("          book_t: {}".format(book_t))
        book_destination = os.path.join(destination, book_p)
        logger.debug("book_destination: {}".format(book_destination))

        if not os.path.exists(book_destination):
            logger.info("EVENT: making {}".format(book_destination))
            if not args.dryrun:
                os.makedirs(book_destination)

        if not book_t in ['.cbr', '.rar']:
            book_destination_f = os.path.join(book_destination, book_f)
            if not os.path.isfile(book_destination_f) or args.replace:
                logger.info("EVENT: copying {} to {}".format(book_f, book_destination))
                if not args.dryrun:
                    if os.path.isfile(book_destination_f):
                        logger.info("EVENT: {} already exists - removing...".format(book_destination_f))
                        # os.unlink(book_destination_f)
                        pass
                    shutil.copyfile(book, book_destination_f)
            logger.debug("----")
            continue

        if book_t in ['.cbr', '.rar']:
            book_z = "{}.cbz".format(book_b)
            logger.debug("          book_z: {}".format(book_z))
            f_book_z = os.path.join(book_destination, book_z)
            logger.debug("        f_book_z: {}".format(f_book_z))
            if not os.path.isfile(os.path.join(book_destination, book_z)) or args.replace:
                with tempfile.TemporaryDirectory() as tmp_x_dir:
                    logger.debug("       tmp_x_dir: {}".format(tmp_x_dir))
                    try:
                        with rarfile.RarFile(book) as rar:
                            logger.info("EVENT: extracting {} to {}".format(book_f, tmp_x_dir))
                            try:
                                rar.extractall(tmp_x_dir)
                            except rarfile.RarWarning as warning:
                                logger.warn("WARNING: Non-fatal error handling {} - some data loss likely.".format(book_f))
                                logger.debug(debug(warning))
                            except rarfile.RarCRCError:
                                logger.error("ERROR: corrupted archive: {}".format(book_f))
                                logger.debug("----")
                                continue
                            except rarfile.BadRarFile:
                                logger.error("ERROR: corrupted archive: {}".format(book_f))
                                logger.debug("----")
                                continue
                    except rarfile.NotRarFile:
                        logger.warn("WARNING: Non-fatal error handling {} - actually a Zip.".format(book_f))
                        if not os.path.isfile(f_book_z) or args.replace:
                            logger.info("EVENT: copying {} to {}".format(book_f, f_book_z))
                            if not args.dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copyfile(book, f_book_z)
                        logger.debug("----")
                        continue
                    except rarfile.RarCRCError:
                        logger.error("ERROR: corrupted archive: {}".format(book_f))
                        logger.debug("----")
                        continue
                    except rarfile.BadRarFile:
                        logger.error("ERROR: corrupted archive: {}".format(book_f))
                        logger.debug("----")
                        continue
                    with tempfile.TemporaryDirectory() as tmp_b_dir:
                        logger.debug("       tmp_b_dir: {}".format(tmp_b_dir))
                        t_book_z = os.path.join(tmp_b_dir, book_z)
                        logger.debug("        t_book_z: {}".format(t_book_z))
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
                            logger.info("EVENT: making {} ".format(t_book_z))
                            for page in pages:
                                logger.debug("            page: {}".format(page))
                                page_f = page[len(tmp_x_dir) + 1:]
                                logger.debug("          page_f: {}".format(page_f))
                                zip.write(page, page_f)
                            zip.close()
                            logger.info("EVENT: copying {} to {}".format(book_z, book_destination))
                            if not args.dryrun:
                                if os.path.isfile(f_book_z):
                                    # os.unlink(f_book_z)
                                    pass
                                shutil.copyfile(t_book_z, f_book_z)
        logger.debug("----")

    logger.info("completed - {} books of {} files.".format(book_count, total))
    logger.info("exiting - success.")

#####


if __name__ == "__main__":
    main()
