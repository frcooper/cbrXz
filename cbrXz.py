#! /usr/bin/python3

import argparse
import inspect
import os
import rarfile
import shutil
import tempfile
import zipfile

BOOK_TYPES = ['.cbr', '.rar', '.cbz', '.zip', '.cb7', '.7z']

def filterBook(s):
  v = False
  if s.startswith("[GER] ") or s.startswith("[FR] "):
    v = True
  return v

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

  log("source: {}".format(source))
  log("destination: {}".format(destination))

  # exit()

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
        log("{} is not a supported filetype.".format(os.path.join(path, f)))

  if args.root is not None:
    root = os.path.abspath(args.root)
    if source.startswith(root):
      source = root
    else:
      log("ERROR: {} is not the child of {}".format(source, root))
      exit()

  log("beginning - {} books of {} files.".format(book_count, total))
  log("----")

  books.sort()
  for book in books:
    log("EVENT: processing {}".format(book))
    # log("            book: {}".format(book))
    t_book = book[len(source) + 1:]
    # log("          t_book: {}".format(t_book))
    book_p, book_f = os.path.split(t_book)
    # log("          book_p: {}".format(book_p))
    # log("          book_f: {}".format(book_f))
    book_b, book_t = os.path.splitext(book_f)
    # log("          book_b: {}".format(book_b))
    # log("          book_t: {}".format(book_t))
    book_destination = os.path.join(destination, book_p)
    # log("book_destination: {}".format(book_destination))

    if not os.path.exists(book_destination):
      log("EVENT: making {}".format(book_destination))
      if not args.dryrun:
        os.makedirs(book_destination)

    if not book_t in ['.cbr', '.rar']:
      book_destination_f = os.path.join(book_destination, book_f)
      if not os.path.isfile(book_destination_f) or args.replace:
        log("EVENT: copying {} to {}".format(book_f, book_destination))
        if not args.dryrun:
          if os.path.isfile(book_destination_f):
            os.unlink(book_destination_f)
          shutil.copyfile(book, book_destination_f)
        log("----")
      continue

    if book_t in ['.cbr', '.rar']:
      book_z = "{}.cbz".format(book_b)
      # log("          book_z: {}".format(book_z))
      f_book_z = os.path.join(book_destination, book_z)
      # log("        f_book_z: {}".format(f_book_z))
      if not os.path.isfile(os.path.join(book_destination, book_z)) or args.replace:
        with tempfile.TemporaryDirectory() as tmp_x_dir:
          # log("       tmp_x_dir: {}".format(tmp_x_dir))
          try:
            with rarfile.RarFile(book) as rar:
              log("EVENT: extracting {} to {}".format(book_f, tmp_x_dir))
              try:
                rar.extractall(tmp_x_dir)
              except rarfile.RarWarning:
                log("WARNING: Non-fatal error handling {} - some data loss likely.".format(book_f))
              except rarfile.RarCRCError:
                log("ERROR: corrupted archive: {}".format(book_f))
                log("----")
                continue
          except rarfile.NotRarFile:
            log("WARNING: Non-fatal error handling {} - actually a Zip.".format(book_f))
            if not os.path.isfile(f_book_z) or args.replace:
              log("EVENT: copying {} to {}".format(book_f, f_book_z))
              if not args.dryrun:
                if os.path.isfile(f_book_z):
                  os.unlink(f_book_z)
                shutil.copyfile(book, f_book_z)
            log("----")
            continue
          with tempfile.TemporaryDirectory() as tmp_b_dir:
            # log("       tmp_b_dir: {}".format(tmp_b_dir))
            t_book_z = os.path.join(tmp_b_dir, book_z)
            # log("        t_book_z: {}".format(t_book_z))
            with zipfile.ZipFile(t_book_z, 'w') as zip:
              pages = []
              for xt_p, xt_fls, xt_fis in os.walk(tmp_x_dir):                                              # pylint: disable=W0612
                for xt_fi in xt_fis:
                  pages.append(os.path.join(xt_p, xt_fi))
              pages.sort()
              log("EVENT: making {} ".format(t_book_z))
              for page in pages:
                # log("            page: {}".format(page))
                page_f = page[len(tmp_x_dir) + 1:]
                # log("          page_f: {}".format(page_f))
                zip.write(page, page_f)
              zip.close()
              log("EVENT: copying {} to {}".format(book_z, book_destination))
              if not args.dryrun:
                if os.path.isfile(f_book_z):
                  os.unlink(f_book_z)
                shutil.copyfile(t_book_z, f_book_z)
    log("----")

  log("completed - {} books of {} files.".format(book_count, total))
  log("exiting - success.")

#####

if __name__ == "__main__":
    main()
