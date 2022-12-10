#
# mymc.py
#
# By Ross Ridge
# Public Domain
#

"""A utility for manipulating PS2 memory card images."""

_SCCS_ID = "@(#) mymc mymc.py 1.13 22/01/15 01:04:45"

import argparse
import sys
import os
import time
import textwrap
from errno import EEXIST, EIO

#import gc
#gc.set_debug(gc.DEBUG_LEAK)

import ps2mc
import ps2save
from ps2mc_dir import *
from round import *
import verbuild

io_error = ps2mc.io_error

if os.name == "nt":
	import codecs

	class file_wrap(object):
		""" wrap a file-like object with a new encoding attribute. """

		def __init__(self, f, encoding):
			object.__setattr__(self, "_f", f)
			object.__setattr__(self, "encoding", encoding)

		def __getattribute__(self, name):
			if name == "encoding":
				return object.__getattribute__(self, name)
			return getattr(object.__getattribute__(self, "_f"),
				       name)

		def __setattr__(self, name, value):
			if name == "encoding":
				raise TypeError("readonly attribute")
			return setattr(object.__getattribute__(self, "_f"),
				       name, value)

	for name in ["stdin", "stdout", "stderr"]:
		f = getattr(sys, name)
		cur = getattr(f, "encoding", None)
		if cur == "ascii" or cur == None:
			f = file_wrap(f, "mbcs")
		else:
			try:
				codecs.lookup(cur)
			except LookupError:
				f = file_wrap(f, "mbcs")
		setattr(sys, name, f)


if os.name in ["nt", "os2", "ce"]:
	from glob import glob
else:
	# assume globing is done by the shell
	glob = lambda pattern: [pattern]


def glob_args(args, globfn):
	ret = []
	for arg in args:
		match = globfn(arg)
		if len(match) == 0:
			ret.append(arg)
		else:
			ret += match
	return ret

def _copy(fout, fin):
	"""copy the contents of one file to another"""

	while True:
		s = fin.read(1024)
		if s == b"":
			break
		fout.write(s)


def do_ls(args, mc, parser):
	mode_bits = "rwxpfdD81C+KPH4"

	out = sys.stdout
	directories = [a.encode() for a in args.directory]
	directories = glob_args(directories, mc.glob)
	for dirname in directories:
		dir = mc.dir_open(dirname)
		try:
			if len(directories) > 1:
				sys.stdout.write("\n" + dirname.decode() + ":\n")
			for ent in dir:
				mode = ent[0]
				if (mode & DF_EXISTS) == 0:
					continue
				for bit in range(0, 15):
					if mode & (1 << bit):
						out.write(mode_bits[bit])
					else:
						out.write("-")
				if args.creation_time:
					tod = ent[3]
				else:
					tod = ent[6]
				tm = time.localtime(tod_to_time(tod))
				out.write(" %7d %04d-%02d-%02d"
					  " %02d:%02d:%02d %s\n"
					  % (ent[2],
					     tm.tm_year, tm.tm_mon, tm.tm_mday,
					     tm.tm_hour, tm.tm_min, tm.tm_sec,
					     ent[8].decode()))
		finally:
			dir.close()


def do_add(args, mc, parser):
	if args.directory != None:
		mc.chdir(args.directory.encode())
	for src in glob_args(args.filename, glob):
		f = open(src, "rb")
		dest = os.path.basename(src)
		out = mc.open(dest.encode(), "wb")
		_copy(out, f)
		out.close()
		f.close()

def do_extract(args, mc, parser):
	if args.directory != None:
		mc.chdir(args.directory.encode())

	close_out = False
	out = None
	if args.output != None:
		if args.use_stdout:
			parser.error("The -o and -p options are mutually exclusive.")
		dont_close_out = True
		out = open(args.output, "wb")
	elif args.use_stdout:
		out = sys.stdout

	filenames = [a.encode() for a in args.filename]
	try:
		for filename in glob_args(filenames, mc.glob):
			f = mc.open(filename, "rb")
			try:
				if out != None:
					_copy(out, f)
					continue
				a = filename.split(b"/")
				o = open(a[-1].decode(), "wb")
				try:
					_copy(o, f)
				finally:
					o.close()
			finally:
				f.close()
	finally:
		if close_out:
			out.close()

def do_mkdir(args, mc, parser):
	for filename in args.directory:
		mc.mkdir(filename.encode())

def do_remove(args, mc, parser):
	for filename in args.filename:
		mc.remove(filename.encode())

def do_import(args, mc, parser):
	filenames = glob_args(args.savefile, glob)
	if args.directory != None and len(filenames) > 1:
		parser.error("The -d option can only be used with a"
			     "single savefile.")

	for filename in filenames:
		sf = ps2save.ps2_save_file()
		f = open(filename, "rb")
		try:
			ftype = ps2save.detect_file_type(f)
			f.seek(0)
			if ftype == "max":
				sf.load_max_drive(f)
			elif ftype == "psu":
				sf.load_ems(f)
			elif ftype == "cbs":
				sf.load_codebreaker(f)
			elif ftype == "sps":
				sf.load_sharkport(f)
			elif ftype == "npo":
				raise io_error(EIO, "nPort saves"
					       " are not supported.",
					       filename)
			else:
				raise io_error(EIO, "Save file format not"
					       " recognized", filename)
		finally:
			f.close()
		dirname = args.directory
		if dirname == None:
			dirname = sf.get_directory()[8].decode()
			target = None
		else:
			dirname = args.directory
			target = args.directory.encode()
		print("Importing", filename, "to", dirname)
		if not mc.import_save_file(sf, args.ignore_existing,
						target):
			print((filename + ": already in memory card image,"
			       " ignored."))

#re_num = re.compile("[0-9]+")

def do_export(args, mc, parser):
	if args.overwrite_existing and args.ignore_existing:
		parser.error("The -i and -f options are mutually exclusive.")

	dirnames = [a.encode() for a in args.dirname]
	dirnames = glob_args(dirnames, mc.glob)
	if args.output_file != None:
		if len(dirnames) > 1:
			parser.error("Only one directory can be exported"
				     " when the -o option is used.")
		if args.longnames:
			parser.error("The -o and -l options are mutually exclusive.")

	if args.directory != None:
		os.chdir(args.directory)

	type = "psu"
	if args.max_drive:
		type = "max"
	for dirname in dirnames:
		sf = mc.export_save_file(dirname)
		filename = args.output_file
		if args.longnames:
			filename = (ps2save.make_longname(dirname, sf).decode()
				    + "." + type)
		if filename == None:
			filename = dirname.decode() + "." + type

		if not args.overwrite_existing:
			exists = True
			try:
				open(filename, "rb").close()
			except EnvironmentError:
				exists = False
			if exists:
				if args.ignore_existing:
					continue
				raise io_error(EEXIST, "File exists", filename)

		f = open(filename, "wb")
		try:
			print("Exporting", dirname.decode(), "to", filename)

			if type == "max":
				sf.save_max_drive(f)
			else:
				sf.save_ems(f)
		finally:
			f.close()

def do_delete(args, mc, parser):
	dirnames = [a.encode() for a in args.dirname]
	for dirname in dirnames:
		mc.rmdir(dirname)

def do_setmode(args, mc, parser):
	set_mask = 0
	clear_mask = ~0
	for (opt, bit) in [(args.read, DF_READ),
			   (args.write, DF_WRITE),
			   (args.execute, DF_EXECUTE),
			   (args.protected, DF_PROTECTED),
			   (args.psx, DF_PSX),
			   (args.pocketstation, DF_POCKETSTN),
			   (args.hidden, DF_HIDDEN)]:
		if opt != None:
			if opt:
				set_mask |= bit
			else:
				clear_mask ^= bit

	value = args.hex_value
	if set_mask == 0 and clear_mask == ~0:
		if value == None:
			parser.error("At least one option must be given.")
		if value.startswith("0x") or value.startswith("0X"):
			value = int(value[2:], 16)
		else:
			value = int(value, 16)
	else:
		if value != None:
			parser.error("The -X option can't be combined with"
				     " other options.")

	filenames = [a.encode() for a in args.filename]
	for arg in glob_args(filenames, mc.glob):
		ent = mc.get_dirent(arg)
		if value == None:
			ent[0] = (ent[0] & clear_mask) | set_mask
			# print "new %04x" % ent[0]
		else:
			ent[0] = value
		mc.set_dirent(arg, ent)

def do_rename(args, mc, parser):
	mc.rename(args.oldname.encode(), args.newname.encode())

def _get_ps2_title(mc, enc):
	s = mc.get_icon_sys(b".")
	if s == None:
		return None
	a = ps2save.unpack_icon_sys(s)
	return ps2save.icon_sys_title(a, enc)

def _get_psx_title(mc, savename, enc):
	mode = mc.get_mode(savename)
	if mode == None or not mode_is_file(mode):
		return None
	f = mc.open(savename)
	s = f.read(128)
	if len(s) != 128:
		return None
	(magic, icon, blocks, title) = struct.unpack("<2sBB64s28x32x", s)
	if magic != b"SC":
		return None
	return [ps2save.shift_jis_conv(zero_terminate(title), enc), ""]

def do_dir(args, mc, parser):
	f = None
	dir = mc.dir_open(b"/")
	try:
		for ent in list(dir)[2:]:
			dirmode = ent[0]
			if not mode_is_dir(dirmode):
				continue
			dirname = b"/" + ent[8]
			mc.chdir(dirname)
			length = mc.dir_size(b".")
			enc = getattr(sys.stdout, "encoding", None)
			if dirmode & DF_PSX:
				title = _get_psx_title(mc, ent[8], enc)
			else:
				title = _get_ps2_title(mc, enc)
			if title == None:
				title = [b"Corrupt", b""]
			protection = dirmode & (DF_PROTECTED | DF_WRITE)
			if protection == 0:
				protection = "Delete Protected"
			elif protection == DF_WRITE:
				protection = "Not Protected"
			elif protection == DF_PROTECTED:
				protection = "Copy & Delete Protected"
			else:
				protection = "Copy Protected"

			type = None
			if dirmode & DF_PSX:
				type = "PlayStation"
				if dirmode & DF_POCKETSTN:
					type = "PocketStation"
			if type != None:
				protection = type

			print("%-32s %s" % (ent[8].decode(), title[0].decode()))
			print(("%4dKB %-25s %s"
			       % (length // 1024, protection, title[1].decode())))
			print()
	finally:
		if f != None:
			f.close()
		dir.close()

	free = mc.get_free_space() // 1024
	if free > 999999:
		free = "%d,%03d,%03d" % (free // 1000000, free // 1000 % 1000,
					 free % 1000)
	elif free > 999:
		free = "%d,%03d" % (free // 1000, free % 1000)
	else:
		free = "%d" % free

	print(free + " KB Free")

def do_df(args, mc, parser):
	print(mc.f.name + ":", mc.get_free_space(), "bytes free.")

def do_check(args, mc, parser):
	if mc.check():
		print("No errors found.")
		return 0
	return 1

def do_format(args, mcname, parser):
	pages_per_card = ps2mc.PS2MC_STANDARD_PAGES_PER_CARD
	if args.clusters != None:
		pages_per_cluster = (ps2mc.PS2MC_CLUSTER_SIZE
				     // ps2mc.PS2MC_STANDARD_PAGE_SIZE)
		pages_per_card = args.clusters * pages_per_cluster
	params = (not args.no_ecc,
		  ps2mc.PS2MC_STANDARD_PAGE_SIZE,
		  ps2mc.PS2MC_STANDARD_PAGES_PER_ERASE_BLOCK,
		  pages_per_card)

	if not args.overwrite_existing:
		exists = True
		try:
			open(mcname, "rb").close()
		except EnvironmentError:
			exists = False
		if exists:
			raise io_error(EEXIST, "file exists", mcname)

	f = open(mcname, "w+b")
	try:
		ps2mc.ps2mc(f, True, params).close()
	finally:
		f.close()

def do_create_pad(args, mc, parser):
	length = mc.clusters_per_card
	if args.length > 0:
		length = args.length
	pad = b"\0" * mc.cluster_size
	f = mc.open(args.filename.encode(), "wb")
	try:
		for i in range(length):
			f.write(pad)
	finally:
		f.close()


def do_frob(args, mc, parser):
	mc.write_superblock()

_trans = bytes.maketrans("".join(map(chr, range(32))).encode(), b" " * 32)

def _print_bin(base, s):
	for off in range(0, len(s), 16):
		print("%04X" % (base + off), end=' ')
		a = s[off : off + 16]
		for b in a:
			print("%02X" % ord(b), end=' ')
		print("", a.translate(_trans).decode())

def _print_erase_block(mc, n):
	ppb = mc.pages_per_erase_block
	base = n * ppb
	for i in range(ppb):
		s = mc.read_page(base + i)
		_print_bin(i * mc.page_size, s)
		print()

def do_print_good_blocks(args, mc, parser):
	print("good_block2:")
	_print_erase_block(mc, mc.good_block2)
	print("good_block1:")
	_print_erase_block(mc, mc.good_block1)

def do_ecc_check(args, mc, parser):
	for i in range(mc.clusters_per_card * mc.pages_per_cluster):
		try:
			mc.read_page(i)
		except ps2mc.ecc_error:
			print("bad: %05x" % i)


def write_error(filename, msg):
	if isinstance(filename, bytes):
		filename = filename.decode()
	if isinstance(filename, str):
		sys.stderr.write(filename + ": ")
	sys.stderr.write(msg + "\n")

if __name__ == '__main__':
	parser = argparse.ArgumentParser(description=__doc__)
	parser.add_argument('-D', '--debug', action='store_true')
	parser.add_argument('-i', '--ignore-ecc', action='store_true',
			    help="Ignore ECC errors while reading.")
	parser.add_argument('-v', '--version', action='version',
			    version=("mymc "
				     + verbuild.MYMC_VERSION_MAJOR
				     + "." + verbuild.MYMC_VERSION_BUILD
				     + "   (" + _SCCS_ID + ")"))
	parser.add_argument('memory_card', default='',
			    help='path to the memory card .ps2 file')

	subparsers = parser.add_subparsers(help='Supported commands')

	parser_ls = subparsers.add_parser("ls", help="List the contents of a directory.")
	parser_ls.add_argument("-c", "--creation-time", action="store_true",
			       help="Display creation times.")
	parser_ls.add_argument('directory', nargs='*', default=["/"])
	parser_ls.set_defaults(file_mode="rb")
	parser_ls.set_defaults(func=do_ls)

	parser_extract = subparsers.add_parser("extract", help="Extract files from the memory card.")
	parser_extract.add_argument("-d", "--directory",
				    help='Extract files from "DIRECTORY".')
	group = parser_extract.add_mutually_exclusive_group()
	group.add_argument("-o", "--output", metavar="FILE",
			   help='Extract file to "FILE".')
	group.add_argument("-p", "--use-stdout", action="store_true",
			   help="Extract files to standard output.")
	parser_extract.add_argument('filename', nargs='+', default=[])
	parser_extract.set_defaults(file_mode="rb")
	parser_extract.set_defaults(func=do_extract)

	parser_add = subparsers.add_parser("add", help="Add files to the memory card.")
	parser_add.add_argument("-d", "--directory",
				help='Add files to "directory".')
	parser_add.add_argument('filename', nargs='+', default=[])
	parser_add.set_defaults(file_mode="r+b")
	parser_add.set_defaults(func=do_add)

	parser_mkdir = subparsers.add_parser("mkdir", help="Make directories.")
	parser_mkdir.add_argument('directory', nargs='+', default=[])
	parser_mkdir.set_defaults(file_mode="r+b")
	parser_mkdir.set_defaults(func=do_mkdir)

	parser_remove = subparsers.add_parser("remove", help="Remove files and directories.")
	parser_remove.add_argument('filename', nargs='+', default=[])
	parser_remove.set_defaults(file_mode="r+b")
	parser_remove.set_defaults(func=do_remove)

	parser_import = subparsers.add_parser("import", help="Import save files into the memory card.")
	parser_import.add_argument("-d", "--directory", metavar="DEST",
				   help='Import to "DEST".')
	parser_import.add_argument("-i", "--ignore-existing", action="store_true",
				   help=("Ignore files that already exist"
					 " on the image."))
	parser_import.add_argument('savefile', nargs='+', default=[])
	parser_import.set_defaults(file_mode="r+b")
	parser_import.set_defaults(func=do_import)

	parser_export = subparsers.add_parser("export", help="Export save files from the memory card.")
	parser_export.add_argument("-d", "--directory",
				   help='Export save files to "directory".')
	group = parser_export.add_mutually_exclusive_group()
	group.add_argument("-f", "--overwrite-existing", action="store_true",
			   help="Overwrite any save files already exported.")
	group.add_argument("-i", "--ignore-existing", action="store_true",
			   help="Ignore any save files already exported.")
	group = parser_export.add_mutually_exclusive_group()
	group.add_argument("-l", "--longnames", action="store_true",
			   help=("Generate longer, more descriptive, filenames."))
	parser_export.add_argument("-m", "--max-drive", action="store_true",
				   help="Use the MAX Drive save file format.")
	group.add_argument("-o", "--output-file", metavar="filename",
			   help='Use "filename" as the name of the save file.')
	parser_export.add_argument("-p", "--ems", action="store_true",
				   help="Use the EMS .psu save file format. [default]")
	parser_export.add_argument('dirname', nargs='+', default=[])
	parser_export.set_defaults(file_mode="rb")
	parser_export.set_defaults(func=do_export)

	parser_delete = subparsers.add_parser("delete", help="Recursively delete a directory (save file).")
	parser_delete.add_argument('dirname', nargs='+', default=[])
	parser_delete.set_defaults(file_mode="r+b")
	parser_delete.set_defaults(func=do_delete)

	parser_set = subparsers.add_parser("set", help="Set mode flags on files and directories")
	parser_set.add_argument("-H", "--hidden", action="store_true",
				help="Set hidden flag")
	parser_set.add_argument("-K", "--pocketstation", action="store_true",
				help="Set PocketStation flag")
	parser_set.add_argument("-P", "--psx", action="store_true",
				help="Set PSX flag")
	parser_set.add_argument("-p", "--protected", action="store_true",
				help="Set copy protected flag")
	parser_set.add_argument("-r", "--read", action="store_true",
				help="Set read allowed flag")
	parser_set.add_argument("-w", "--write", action="store_true",
				help="Set write allowed flag")
	parser_set.add_argument("-X", "--hex-value", metavar="mode",
				help='Set mode to "mode".')
	parser_set.add_argument("-x", "--execute", action="store_true",
				help="Set executable flag")
	parser_set.add_argument('filename', nargs='+', default=[])
	parser_set.set_defaults(file_mode="r+b")
	parser_set.set_defaults(func=do_setmode)

	parser_clear = subparsers.add_parser("clear", help="Clear mode flags on files and directories")
	parser_clear.add_argument("-H", "--hidden", action="store_false",
				  help="Clear hidden flag")
	parser_clear.add_argument("-K", "--pocketstation", action="store_false",
				  help="Clear PocketStation flag")
	parser_clear.add_argument("-P", "--psx", action="store_false",
				  help="Clear PSX flag")
	parser_clear.add_argument("-p", "--protected", action="store_false",
				  help="Clear copy protected flag")
	parser_clear.add_argument("-r", "--read", action="store_false",
				  help="Clear read allowed flag")
	parser_clear.add_argument("-w", "--write", action="store_false",
				  help="Clear write allowed flag")
	parser_clear.add_argument("-X", "--hex-value",
				  help='Clear mode to "mode".')
	parser_clear.add_argument("-x", "--execute", action="store_false",
				  help="Clear executable flag")
	parser_clear.add_argument('filename', nargs='+', default=[])
	parser_clear.set_defaults(file_mode="r+b")
	parser_clear.set_defaults(func=do_setmode)

	parser_rename = subparsers.add_parser("rename", help="Rename a file or directory")
	parser_rename.add_argument('oldname')
	parser_rename.add_argument('newname')
	parser_rename.set_defaults(file_mode="r+b")
	parser_rename.set_defaults(func=do_rename)

	parser_dir = subparsers.add_parser("dir", help="Display save file information.")
	parser_dir.set_defaults(file_mode="rb")
	parser_dir.set_defaults(func=do_dir)

	parser_df = subparsers.add_parser("df", help="Display the amount free space.")
	parser_df.set_defaults(file_mode="rb")
	parser_df.set_defaults(func=do_df)

	parser_check = subparsers.add_parser("check", help="Check for file system errors.")
	parser_check.set_defaults(file_mode="rb")
	parser_check.set_defaults(func=do_check)

	parser_format = subparsers.add_parser("format", help="Creates a new memory card image.")
	parser_format.add_argument("-c", "--clusters", type=int,
				   help="Size in clusters of the memory card.")
	parser_format.add_argument("-e", "--no-ecc", action="store_true",
				   help="Create an image without ECC")
	parser_format.add_argument("-f", "--overwrite-existing", action="store_true",
				   help="Overwrite any existing file")
	parser_format.set_defaults(file_mode=None)
	parser_format.set_defaults(func=do_format)

	#
	# secret commands for debugging purposes.
	#

	parser_frob = subparsers.add_parser("frob")
	parser_frob.set_defaults(file_mode="r+b")
	parser_frob.set_defaults(func=do_frob)

	parser_print_good_blocks = subparsers.add_parser("print_good_blocks")
	parser_print_good_blocks.set_defaults(file_mode="rb")
	parser_print_good_blocks.set_defaults(func=do_print_good_blocks)

	parser_ecc_check = subparsers.add_parser("ecc_check")
	parser_ecc_check.set_defaults(file_mode="rb")
	parser_ecc_check.set_defaults(func=do_ecc_check)

	parser_create_pad = subparsers.add_parser("create_pad")
	parser_create_pad.add_argument('filename')
	parser_create_pad.add_argument('-l', '--length', type=int, default=0)
	parser_create_pad.set_defaults(file_mode="r+b")
	parser_create_pad.set_defaults(func=do_create_pad)

	args = parser.parse_args()


	f = None
	mc = None
	ret = 0
	mcname = args.memory_card

	try:
		try:
			if args.file_mode == None:
				ret = args.func(args, mcname, parser)
			else:
				f = open(mcname, args.file_mode)
				mc = ps2mc.ps2mc(f, args.ignore_ecc)
				ret = args.func(args, mc, parser)
		finally:
			if mc != None:
				mc.close()
			if f != None:
				# print "f.close()"
				f.close()

	except EnvironmentError as value:
		if getattr(value, "filename", None) != None:
			write_error(value.filename, value.strerror)
			ret = 1
		elif getattr(value, "strerror", None) != None:
			write_error(mcname, value.strerror)
			ret = 1
		else:
			# something weird
			raise
		if args.debug:
			raise

	except (ps2mc.error, ps2save.error) as value:
		fn = getattr(value, "filename", None)
		if fn == None:
			fn = mcname
		write_error(fn, str(value))
		if args.debug:
			raise
		ret = 1

	if ret == None:
		ret = 0

	parser.exit(ret)
