import multiprocessing
import nibabel as nib
import numpy as np
from scipy.io import loadmat
from scipy import sparse
from itertools import compress
import os
import sys
import time
import argparse

def argument_parse():
	parser=argparse.ArgumentParser()

	parser.add_argument('--chunklist',action='store', dest='chunklist', required=True)
	parser.add_argument('--fileroot',action='store', dest='fileroot', required=True)
	parser.add_argument('--outputdir',action='store', dest='outdir', required=True)
	parser.add_argument('--lesionfile',action='store', dest='lesionfile')
	parser.add_argument('--algo','-a',action='store', dest='algo',default='ifod2act5Mfsl')
	parser.add_argument('--numtracks','-n',action='store', dest='numtracks',default='5M')

	return parser.parse_args()
    
#takes 60 seconds per subject for full 2280 set with csr_matrix(A) up front
#ORDERS OF MAGNITUDE slower if we save the csr_matrix(chunk) for the end
#similarly SLOW SLOW SLOW if we just keep it all in csc_matrix....
def savechunks(sparselist,subjsplitidx,whichsplit):
	#externals: outdir
	#zeromat=sparse.csc_matrix((chunksize,numtracks),dtype=np.uint8)>0

	subjidx_split=np.where(subjsplitidx==whichsplit)[0]
	sparsefiles_split=list(compress(sparselist,subjsplitidx==whichsplit))
	#subjchunks_split=list(compress(subjchunks,subjsplitidx==whichsplit))

	subjchunkA=[]
	subjcount=0
	starttime=time.time()
	for isp,sf in enumerate(sparsefiles_split):
		subjidx=subjidx_split[isp]
		#continue
		A=sparse.csr_matrix(loadmat(sf,variable_names=['A'])['A'])
		#A=loadmat(sf)['A']
		for whichchunk in chunks_to_save:
			#chunkA=M['A'][chunkidx_flat==whichchunk,:]>0
			#subjchunkA.append(chunkA)

			chunkfilename=outdir+'/chunkdir%05d/chunk%05d_subj%05d.npz' % (whichchunk,whichchunk,subjidx)
			#print(chunkfilename)
			sparse.save_npz(chunkfilename,A[chunkidx_flat==whichchunk,:]>0,compressed=False)

		nowtime=time.time()
		print('split=%3d subj=%5d %.3f seconds (%.3f/subj)' % (whichsplit,isp,nowtime-starttime,(nowtime-starttime)/(isp+1)))

def mergechunks(chunklist, chunksplitidx, whichsplit):
	#externals: outdir
	chunklist_split=list(compress(chunklist,chunksplitidx==whichsplit))
	for ich,whichchunk in enumerate(chunklist_split):
		subjchunkA=[]
		startchunktime=time.time()
		for isp,subj in enumerate(subjects):
			chunkfilename_subj=outdir+'/chunkdir%05d/chunk%05d_subj%05d.npz' % (whichchunk,whichchunk,isp)
			subjchunkA.append(sparse.load_npz(chunkfilename_subj))
		chunkfilename=chunkfile_fmt % (whichchunk)
		sparse.save_npz(chunkfilename,sparse.vstack(subjchunkA),compressed=False)
		if ich > 0 and ich % 10 == 0:
			print('split=%3d %d/%d merged: %.3f seconds' % (whichsplit,ich,len(chunklist_split),time.time()-startchunktime))

if __name__ == "__main__":
	args=argument_parse()
	chunklistfile=args.chunklist
	fileroot=args.fileroot
	outdir=args.outdir
	lesionfile=args.lesionfile
	algo=args.algo
	numtrackstr=args.numtracks

	#subjfid=open(subjectlistfile,'r')
	#subjects=[x.strip() for x in subjfid.readlines()]
	#subjfid.close()
	chunklist=np.load(chunklistfile)
	subjects=chunklist["subjects"]
	chunksize=chunklist["chunksize"]
	chunkidx_flat=chunklist["chunkidx_flat"].copy()
	unique_chunks=chunklist["unique_chunks"].copy()

	#subjects=subjects[:10]

	#algo='ifod2act5Mfsl'
	#numtrackstr='5M'

	num_cpu=multiprocessing.cpu_count()
	
	#numsubjsplits=num_cpu-1
	numsubjsplits=int(num_cpu/2)-1
	numsubj=len(subjects)
	subjsplitidx=np.floor(numsubjsplits*np.arange(numsubj)/numsubj)

	os.makedirs(outdir,exist_ok=True)

	if lesionfile is None:
		chunks_to_save=unique_chunks
	else:
		Limg=nib.load(lesionfile)
		Ldata=Limg.get_fdata()
		if Ldata.shape == (182,218,182):
			#seems correct
			pass
		elif Ldata.shape == (181,217,181):
			print('Input was 181x217x181, not the expected 182x218x181. Assuming SPM-based reg and padding end of each dim.')
			Ldata=np.pad(Ldata,(0,1),mode='constant')
		else:
			raise('Unexpected size: (%d,%d,%d). Input must be registered to 182x218x182 MNIv6 template (FSL template)', (Ldata.shape))
		Lmask=Ldata.flatten()>0
		chunks_to_save=np.unique(chunkidx_flat[Lmask])


	#for disk-access heavy, keep it to half the total "cores" (since its actually hyperthreading)
	numchunksplits=int(num_cpu/2)-1
	numchunk=len(chunks_to_save)
	chunksplitidx=np.floor(numchunksplits*np.arange(numchunk)/numchunk)


	#############

	sparsefiles=[]
	for subj in subjects:
		sparsefiles.append('%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr))

	numtracks=loadmat(sparsefiles[0],variable_names=['A'])['A'].shape[1]

	chunkfile_fmt=outdir+'/chunk%05d.npz'
	chunkfile_split_fmt=outdir+'/chunk%05d_split%02d.npz'

	for ichunk in chunks_to_save:
		os.makedirs(outdir+'/chunkdir%05d' % (ichunk),exist_ok=True)


	#######################

	starttime=time.time()
	processes=[]
	for pi in range(numsubjsplits):
		p=multiprocessing.Process(target=savechunks,args=(sparsefiles,subjsplitidx,pi))
		processes.append(p)
		p.start()

	for process in processes:
		process.join()

	print('total time to create subjfiles: %.3f seconds' % (time.time()-starttime))

	startmergetime=time.time()
	processes=[]
	for pi in range(numchunksplits):
		p=multiprocessing.Process(target=mergechunks,args=(chunks_to_save,chunksplitidx,pi))
		processes.append(p)
		p.start()

	for process in processes:
		process.join()

	print('Total merge took %.3f seconds' % (time.time()-startmergetime))

	######################
	#add chunk file size to chunklist info
	chunklist=dict(np.load(chunklistfile))

	chunkfilesize=np.zeros((chunklist['numchunks'],))
	chunkfilesize[unique_chunks]=[os.path.getsize(chunkfile_fmt % (whichchunk)) for whichchunk in unique_chunks]
	#don't save it as a sparse because 1) its not very big and 2) it requires "allow_pickle=True" every time we np.load
	#chunkfilesize=sparse.csr_matrix(chunkfilesize)
	chunklist['chunkfilesize']=chunkfilesize.astype(np.float32)
	np.savez(chunklistfile,**dict(chunklist))

