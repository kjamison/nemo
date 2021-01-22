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

def savechunks(sparselist,subjsplitidx,whichsplit,whichchunk):
	#externals: chunksize, numtracks, chunkfile_split_fmt
	zeromat=sparse.csc_matrix((chunksize,numtracks),dtype=np.uint8)>0

	sparsefiles_split=list(compress(sparselist,subjsplitidx==whichsplit))
	#subjchunks_split=list(compress(subjchunks,subjsplitidx==whichsplit))

	subjchunkA=[]
	subjcount=0
	starttime=time.time()
	for isp,sf in enumerate(sparsefiles_split):
		#if not whichchunk in subjchunks_split[isp]:
		#    subjchunkA.append(zeromat)
		#    continue
		M=loadmat(sf)
		#chunkA=M['A'][chunkidx_flat==whichchunk,:]>0
		A=sparse.csr_matrix(M['A'])
		chunkA=A[chunkidx_flat==whichchunk,:]>0
		#subjchunkA.append(chunkA)
		subjchunkA=sparse.vstack((subjchunkA,chunkA))
		subjcount+=1
		nowtime=time.time()
		print('split=%3d subj=%5d chunk=%05d %.3f seconds (%.3f/subj)' % (whichsplit,isp,whichchunk,nowtime-starttime,(nowtime-starttime)/(isp+1)))

	#if subjcount==0:
	#    print('No subjects for chunk %d_%d' % (ichunk,whichsplit))
	#    continue
	#print(whichsplit,whichchunk,len(subjchunkA))
	chunkfilename=chunkfile_split_fmt % (whichchunk,whichsplit)
	#sparse.save_npz(chunkfilename,sparse.vstack(subjchunkA),compressed=False)
	sparse.save_npz(chunkfilename,subjchunkA,compressed=False)

if __name__ == "__main__":
	args=argument_parse()
	#subjectlistfile=sys.argv[1]
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


	numsubjsplits=1
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

	#############

	sparsefiles=[]
	for subj in subjects:
		sparsefiles.append('%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr))

	numtracks=loadmat(sparsefiles[0])['A'].shape[1]

	chunkfile_fmt=outdir+'/chunk%05d.npz'
	chunkfile_split_fmt=outdir+'/chunk%05d_split%02d.npz'

	for ichunk in chunks_to_save:
	    chunkfilename=chunkfile_fmt % (ichunk)
	    if os.path.exists(chunkfilename):
	        print('%s already exists' % (chunkfilename))
	        continue
	    starttime=time.time()
	    processes=[]
	    for pi in range(numsubjsplits):
	        p=multiprocessing.Process(target=savechunks,args=(sparsefiles,subjsplitidx,pi,ichunk))
	        processes.append(p)
	        p.start()

	    for process in processes:
	        process.join()
    
	    print('chunk%05d_xx total time: %.3f seconds' % (ichunk,time.time()-starttime))
    
	    subjchunkA=[]
	    for pi in range(numsubjsplits):
	        chunkfilename_split=chunkfile_split_fmt % (ichunk,pi)
	        subjchunkA.append(sparse.load_npz(chunkfilename_split))
	        os.remove(chunkfilename_split)
    
	    sparse.save_npz(chunkfilename,sparse.vstack(subjchunkA),compressed=False)
	    print('chunk%05d total time: %.3f seconds' % (ichunk,time.time()-starttime))
	#savechunks(sparsefiles,subjsplitidx,0)

