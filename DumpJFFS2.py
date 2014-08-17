import sys
import struct
import pprint
import os
from zlib import decompress,compress
import shutil
import zlib

JFFS2_COMPR_NONE	= 0x00
JFFS2_COMPR_ZERO	= 0x01
JFFS2_COMPR_RTIME	= 0x02
JFFS2_COMPR_RUBINMIPS	= 0x03
JFFS2_COMPR_COPY	= 0x04
JFFS2_COMPR_DYNRUBIN	= 0x05
JFFS2_COMPR_ZLIB	= 0x06
JFFS2_COMPR_LZO	= 0x07

# Compatibility flags. 
JFFS2_COMPAT_MASK	= 0xc000 
JFFS2_NODE_ACCURATE	= 0x2000

# INCOMPAT: Fail to mount the filesystem 
JFFS2_FEATURE_INCOMPAT	= 0xc000

# ROCOMPAT: Mount read-only 
JFFS2_FEATURE_ROCOMPAT	= 0x8000

# RWCOMPAT_COPY: Mount read/write, and copy the node when it's GC'd 
JFFS2_FEATURE_RWCOMPAT_COPY	= 0x4000

# RWCOMPAT_DELETE: Mount read/write, and delete the node when it's GC'd 
JFFS2_FEATURE_RWCOMPAT_DELETE	= 0x0000
JFFS2_NODETYPE_DIRENT	= (JFFS2_FEATURE_INCOMPAT | JFFS2_NODE_ACCURATE | 1)
JFFS2_NODETYPE_INODE	= (JFFS2_FEATURE_INCOMPAT | JFFS2_NODE_ACCURATE | 2)
JFFS2_NODETYPE_CLEANMARKER	= (JFFS2_FEATURE_RWCOMPAT_DELETE | JFFS2_NODE_ACCURATE | 3)
JFFS2_NODETYPE_PADDING	= (JFFS2_FEATURE_RWCOMPAT_DELETE | JFFS2_NODE_ACCURATE | 4)
JFFS2_NODETYPE_SUMMARY	= (JFFS2_FEATURE_RWCOMPAT_DELETE | JFFS2_NODE_ACCURATE | 6)
JFFS2_NODETYPE_XATTR	= (JFFS2_FEATURE_INCOMPAT | JFFS2_NODE_ACCURATE | 8)
JFFS2_NODETYPE_XREF	= (JFFS2_FEATURE_INCOMPAT | JFFS2_NODE_ACCURATE | 9)

# XATTR Related 
JFFS2_XPREFIX_USER	= 1 # for "user." 
JFFS2_XPREFIX_SECURITY	= 2 # for "security." 
JFFS2_XPREFIX_ACL_ACCESS	= 3 # for "system.posix_acl_access" 
JFFS2_XPREFIX_ACL_DEFAULT	= 4 # for "system.posix_acl_default" 
JFFS2_XPREFIX_TRUSTED	= 5 # for "trusted.*" 
JFFS2_ACL_VERSION	= 0x0001
JFFS2_NODETYPE_CHECKPOINT	= (JFFS2_FEATURE_RWCOMPAT_DELETE | JFFS2_NODE_ACCURATE | 3)
JFFS2_NODETYPE_OPTIONS	= (JFFS2_FEATURE_RWCOMPAT_COPY | JFFS2_NODE_ACCURATE | 4)
JFFS2_INO_FLAG_PREREAD	= 1 # Do read_inode() for this one at
JFFS2_INO_FLAG_USERCOMPR	= 2 # User has requested a specific


header_unpack_fmt="<HHL"
header_struct_size=struct.calcsize(header_unpack_fmt)

inode_unpack_fmt="<LLLLHHLLLLLLLBBHLL"
inode_struct_size=struct.calcsize(inode_unpack_fmt)

dirent_unpack_fmt="<LLLLLBBBLL"
dirent_struct_size=struct.calcsize(dirent_unpack_fmt)

class JFFS:
	DebugLevel=0
	DumpMagicError=False
	def __init__(self):
		pass

	def Parse(self,filename, pattern=''):
		self.OrigFilename=filename
		fd=open(filename,'rb')
		data=fd.read()
		fd.close()
	
		data_offset = 0
		total_count = 0
		
		last_magic = 0
		last_nodetype = 0
		last_totlen = 0
		last_data_offset = 0
		
		self.INodeMap = {}
		self.DirentMap = {}
		
		while 1:
			error=False
		
			hdr=data[data_offset:data_offset+header_struct_size]
			try:
				(magic,nodetype,totlen) = struct.unpack(header_unpack_fmt, hdr)
			except:
				break
		
			if magic!=0x1985:
				if self.DumpMagicError:
					print '* Magic Error:', hex(data_offset), "(", hex(magic), ",", hex(nodetype), ")" 
					print '\tLast record:', hex(last_data_offset), "(", hex(last_magic), ",", hex(last_nodetype), ",", hex(last_totlen), ")" 

				while data_offset < len(data):
					tag = data[data_offset:data_offset+4]
					if tag=='\x85\x19\x02\xe0':
						if self.DumpMagicError:
							print '\tFound next inode at 0x%x' % data_offset
							print ''

						break
					data_offset+=0x4
			
				if data_offset < len(data):
					(magic, nodetype,totlen) = struct.unpack(header_unpack_fmt, data[data_offset:data_offset+header_struct_size])
		
				if magic!=0x1985:
					break
		
			if nodetype==JFFS2_NODETYPE_INODE:
				node_data = data[data_offset+header_struct_size:data_offset+header_struct_size+inode_struct_size]
				(hdr_crc, ino, version, mode, uid, gid, isize, atime, mtime, ctime, offset, csize, dsize, compr, usercompr, flags, data_crc, node_crc) = struct.unpack(inode_unpack_fmt, node_data)
		
				payload = data[data_offset+0x44: data_offset+0x44+csize]
				
				if compr == 0x6:
					try:
						payload=decompress(payload)
					except:
						if self.DebugLevel>0:
							print "* Uncompress error"
							error=True
						pass
	
					if self.DebugLevel>0:
						print "payload length:", len(payload)
		
				if self.DebugLevel>1:
					pprint.pprint(payload)
		
				if not self.INodeMap.has_key(ino):
					self.INodeMap[ino] = []
		
				self.INodeMap[ino].append( {
						"data_offset": data_offset,
						"ino": ino,
						"hdr_crc": hdr_crc, 
						"version": version, 
						"mode": mode, 
						"uid": uid, 
						"gid": gid, 
						"isize": isize, 
						"atime": atime, 
						"mtime": mtime, 
						"ctime": ctime, 
						"offset": offset, 
						"csize": csize, 
						"dsize": dsize, 
						"compr": compr, 
						"usercompr": usercompr, 
						"flags": flags, 
						"data_crc": data_crc, 
						"node_crc": node_crc, 
						"payload": payload
					})
		
				if error or (pattern!='' and self.DirentMap.has_key(ino) and self.DirentMap[ino]['payload'].find(pattern)>=0):
					print '='*79
					print '* JFFS2_NODETYPE_INODE:'
					print 'data_offset:\t',hex(data_offset)
					print "magic:\t\t%x" % magic
					print "nodetype:\t%x" % nodetype
					print "totlen:\t\t%x" % totlen
					print "hdr_crc:\t%x" % hdr_crc
					print "ino:\t\t%x" % ino
					print "version:\t%x" % version
					print "mode:\t\t%x" % mode
					print "uid:\t\t%x" % uid
					print "gid:\t\t%x" % gid
					print "isize:\t\t%x" % isize
					print "atime:\t\t%x" % atime
					print "mtime:\t\t%x" % mtime
					print "ctime:\t\t%x" % ctime
					print "offset:\t\t%x" % offset
					print "csize:\t\t%x" % csize
					print "dsize:\t\t%x" % dsize
					print "compr:\t\t%x" % compr
					print "usercompr:\t%x" % usercompr
					print "flags:\t\t%x" % flags
					print "data_crc:\t%x" % data_crc
					print "node_crc:\t%x" % node_crc
					print len(self.INodeMap[ino])
					print ''
		
		
			elif nodetype==JFFS2_NODETYPE_DIRENT:
				(hdr_crc, pino, version, ino, mctime, nsize, ent_type, unused, node_crc, name_crc) = struct.unpack(dirent_unpack_fmt, data[data_offset+header_struct_size:data_offset+header_struct_size+dirent_struct_size])
				payload = data[data_offset+header_struct_size+dirent_struct_size+1: data_offset+header_struct_size+dirent_struct_size+1+nsize]

				if not self.DirentMap.has_key(ino) or self.DirentMap[ino]['version']<version:
					self.DirentMap[ino] = {
							"hdr_crc": hdr_crc, 
							"pino": pino, 
							"version": version, 
							"mctime": mctime, 
							"nsize": nsize, 
							"ent_type": ent_type, 
							"node_crc": node_crc, 
							"name_crc": name_crc, 
							"payload": payload
						}
		
				if pattern!='' and payload.find(pattern)>=0:
					print '='*79
					print '* JFFS2_NODETYPE_DIRENT:'
					print 'data_offset:\t',hex(data_offset)
					print "magic:\t\t%x" % magic
					print "nodetype:\t%x" % nodetype
					print "totlen:\t\t%x" % totlen
					print "hdr_crc:\t%x" % hdr_crc
					print "pino:\t\t%x" % pino
					print "version:\t%x" % version
					print "ino:\t\t%x" % ino
					print "node_crc:\t%x" % node_crc

					parent_node=''
					if self.DirentMap.has_key(pino):
						parent_node=self.DirentMap[pino]['payload']

					print "Payload:\t%s" % (parent_node + "\\" + payload)
					print ''
		
			elif nodetype==0x2004:
				pass
		
			else:
				print '='*79
				print 'data_offset:\t',hex(data_offset)
				print "magic:\t\t%x" % magic
				print "nodetype:\t%x" % nodetype
				print "totlen:\t\t%x" % totlen
				
			(last_magic, last_nodetype, last_totlen) = (magic, nodetype, totlen)
		
			last_data_offset = data_offset
		
			if totlen%4 !=0 :
				totlen += 4-(totlen%4)
			
			data_offset += totlen
		
			current_page_data_len = data_offset % 0x200 
			if (0x200-current_page_data_len) < 0x8:
				data_offset += 0x200-current_page_data_len
	
			if self.DebugLevel>0:
				print '* Record (@%x):\tMagic: %x\tType: %x\tTotlen %x\tPadded Totlen: %x' % (last_data_offset, last_magic, last_nodetype, last_totlen, totlen)
			total_count += 1
		
		print "Total Count:",total_count
		if self.DebugLevel>0:
			pprint.pprint(self.DirentMap)
	
	def GetPath(self,ino):
		path=''

		while ino!=0 and self.DirentMap.has_key(ino):
			path = '/' + self.DirentMap[ino]['payload'] + path
			ino=self.DirentMap[ino]['pino']

		return path

	def GetData(self,inode_map_record,dump=False):
		data=[]
		for record in inode_map_record:
			if dump:
				print len(inode_map_record)
				print "\tVersion: %x Offset: %x DSize: %x Data Offset: %x Payload Length: %x" % (record['version'], record['offset'], record['dsize'], record['data_offset'], len(record['payload']))

			offset = record['offset']
			dsize=record['dsize']

			new_data_len=offset+dsize-len(data)

			if new_data_len>0:
				data+=['\x00'] * new_data_len

			data[offset:offset+dsize]=record['payload']

		return ''.join(data)

	def GetDataSeq(self,inode_map_record,dump=False):
		next_offset=0
		data=''

		for record in inode_map_record:
			if dump:
				print len(inode_map_record)
				print "Version: %x Offset: %x DSize: %x Data Offset: %x Payload Length: %x" % (record['version'], record['offset'], record['dsize'], record['data_offset'], len(record['payload']))

			offset = record['offset']
			if offset == next_offset:
				next_offset = offset + record['dsize']
				found_record=True
				data += record['payload']
	
		return data

	def WriteData(self,output_filename,inode_map_record,data):
		shutil.copy(self.OrigFilename, output_filename)

		next_offset=0
		while 1:
			found_record=False
			for record in inode_map_record:
				offset = record['offset']

				if offset == next_offset:
					orig_data=data
					if record['compr'] == 0x6:
						try:
							data=compress(data)
						except:
							print "* Compress error"
						
					print 'data_offset: %x offset: %x dsize: %x csize: %x' % (record['data_offset'], record['offset'], record['dsize'], record['csize'])
					print 'Trying to write: %x' % len(data)

					if record['csize'] > len(data):
						fd=open(output_filename,'r+')
						fd.seek(record['data_offset'])
						
						record['csize']=len(data)
						record['dsize']=len(orig_data)

						fd.write(struct.pack(inode_unpack_fmt,
												record['hdr_crc'],
												record['ino'],
												record['version'],
												record['mode'],
												record['uid'],
												record['gid'],
												record['isize'],
												record['atime'],
												record['mtime'],
												record['ctime'],
												record['offset'],
												record['csize'],
												record['dsize'],
												record['compr'],
												record['usercompr'],
												record['flags'],
												record['data_crc'],
												record['node_crc']
										) + data + (record['csize'] - len(data)) * '\xFF')
						fd.close()

					next_offset = offset + record['dsize']
	
					if next_offset != offset:
						found_record=True
					break
		
			if not found_record:
				break
	
		return data

	def DumpFile(self, filename, mod='', out=''):
		print 'DumpFile'
		for ino in self.DirentMap.keys():
			if self.INodeMap.has_key(ino):
				path=self.GetPath(ino)

				if path==filename:
					print ''
					print '='*80
					print ino, self.GetPath(ino), len(self.DirentMap[ino]["payload"])
					pprint.pprint(self.DirentMap[ino])
					 
					data = self.GetData(self.INodeMap[ino])
					print data

					if mod!='':
						fd=open(mod,'rb')
						self.WriteData(out,self.INodeMap[ino], fd.read())
						fd.close()

	def DumpIno(self,output_dir,ino,pattern=''):

		path=self.GetPath(ino)

		dir=os.path.dirname(path)
		basename=os.path.basename(path)

		local_dir=os.path.join(output_dir, dir[1:])
		local_path=os.path.join(local_dir, basename)

		dump=False
		if pattern!='' and path.find(pattern)>=0:
			dump=True

		if dump:
			print 'File %s (ino: %d)' % (path, ino)

		data = self.GetData(self.INodeMap[ino], dump=dump)

		if dump:
			print '\tFile length %d' % (len(data))

		if len(data)==0:
			return

		if not os.path.isdir(local_dir):
			os.makedirs(local_dir)

		try:
			fd=open(local_path,"wb")
			fd.write(data)
			fd.close()
		except:
			print "Failed to create file: %s" % (local_path)
			pass

	def Dump(self,output_dir,pattern=''):
		if not os.path.isdir(output_dir):
			os.makedirs(output_dir)

		processed_ino={}
		for ino in self.DirentMap.keys():
			if self.INodeMap.has_key(ino):
				processed_ino[ino]=True
				self.DumpIno(output_dir,ino,pattern)

		for ino in self.INodeMap.keys():
			if not processed_ino.has_key(ino):
				self.DumpIno(output_dir,ino,pattern)

	def ListData(self,inode_map_record):
		for record in inode_map_record:
			offset = record['offset']
			print 'version: 0x%x' % record['version']
			print '\toffset: 0x%x' % record['offset']
			print '\tpayload: 0x%x' % len(record['payload'])
			print '\tdata_offset: 0x%x' % record['data_offset']
			print '\tctime: 0x%x' % record['ctime']
			print '\tmtime: 0x%x' % record['mtime']
			print '\tatime: 0x%x' % record['atime']

	def ListFile(self,filename):
		print 'Path\tInode\tNumber of records'
		for ino in self.DirentMap.keys():
			if self.INodeMap.has_key(ino):
				if filename=='':
					print self.GetPath(ino)
					print '\tInode:', ino
					print '\tRecords:', len(self.INodeMap[ino])
				else:
					path=self.GetPath(ino)
					if path==filename:
						print self.GetPath(ino)
						print '\tInode:', ino
						print '\tRecords:', len(self.INodeMap[ino])
						self.ListData(self.INodeMap[ino])

if __name__=='__main__':
	from optparse import OptionParser

	parser = OptionParser()
	parser.add_option("-o", "--output_dir", dest="output_dir",
                  help="Set output directory name", default="", metavar="OUTPUT_DIR")

	parser.add_option("-f", "--file", dest="file",
                  help="Set target filename", default="", metavar="FILE")

	parser.add_option("-n", "--new_data_filename", dest="new_data_filename",
                  help="Set new data file name", default="", metavar="NEW_DATA_FILENAME")

	parser.add_option("-O", "--output_filename", dest="output_filename",
                  help="Set output filename", default="", metavar="OUTPUT_FILENAME")

	parser.add_option("-l", action="store_true", dest="list")

	(options, args) = parser.parse_args()

	filename = args[0]

	jffs = JFFS()
	jffs.Parse(filename, pattern=options.file)

	if options.list:
		jffs.ListFile(options.file)
	elif options.output_dir!='':
		print 'Dumping files to a folder: %s' % (options.output_dir)
		jffs.Dump(options.output_dir, pattern=options.file)
	elif options.file!='':
		jffs.DumpFile(options.file, options.new_data_filename, options.output_filename)
	