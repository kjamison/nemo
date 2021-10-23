import numpy as np
from scipy.io import loadmat
from scipy import sparse
import sys
import time
import glob
import os
import multiprocessing
from itertools import compress
import argparse

def argument_parse():
	parser=argparse.ArgumentParser()

	parser.add_argument('--chunklist',action='store', dest='chunklist', required=True)
	parser.add_argument('--fileroot',action='store', dest='fileroot', required=True)
	parser.add_argument('--output',action='store', dest='outfile', required=True)
	parser.add_argument('--outputmask',action='store', dest='outmaskfile')
	parser.add_argument('--algo','-a',action='store', dest='algo',default='ifod2act5Mfsl')
	parser.add_argument('--numtracks','-n',action='store', dest='numtracks',default='5M')

	return parser.parse_args()

def save_endpoints(subjlist,outfile1,outfile2):
	#externals: algo, numtrackstr, fileroot
	endpoint1=[]
	endpoint2=[]

	print('Starting %d subjects in %s' % (len(subjlist),outfile1))
	starttime=time.time()
	for isubj,subj in enumerate(subjlist):
		sparsefile='%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr)
		B=sparse.coo_matrix(loadmat(sparsefile,variable_names=['B'])['B'])
		i=B.row
		j=B.col
		idx=np.argsort(i)
		isort=i[idx]
		jsort=j[idx]
	    #B generally does NOT contain 10M nonzeros, usually has a few hundred fewer. why?
	    #when we read in track data, the streamlines are initially concatenated and separated by nans
	    #when we store this, we remove sequential dupes and we store data[~dnan]
	    #so apparently a few hundred streamlines only have a few duplicate voxels and thus don't end up
	    #in the final sparsemat?
	    #Then when we store in endpoint1 and endpoint2, some of the streamline endpoints are STILL "voxel 0" after filling in
	    #because they didn't have a value for that streamline
		if len(endpoint1) == 0:
			endpoint1=np.zeros((len(subjlist),B.shape[0]),dtype=np.uint32)
			endpoint2=np.zeros((len(subjlist),B.shape[0]),dtype=np.uint32)
			#print('endpoint1: (%d,%d)' % (endpoint1.shape))
		endpoint1[isubj,isort[0::2]]=jsort[0::2]
		endpoint2[isubj,isort[1::2]]=jsort[1::2]
		if isubj > 0 and isubj % 10 == 0:
			print('%d/%d in %s' % (isubj,len(subjlist),outfile1))

	np.save(outfile1,endpoint1)
	np.save(outfile2,endpoint2)
	print('%s took %.3f seconds' % (outfile1,time.time()-starttime))
    
def make_endpoint_mask(isubj):
	#externals: endpointmat, numsubj, numvoxels
	endpt=endpointmat[(isubj,isubj+numsubj),:].flatten()
	#!!!!!return sparse.csr_matrix((np.ones(endpt.size,dtype=bool),(np.zeros(endpt.size),endpt)),shape=(1,numvoxels))>0
	return sparse.csr_matrix((np.ones(endpt.size,dtype=np.int32),(np.zeros(endpt.size),endpt)),shape=(1,numvoxels))

if __name__ == "__main__":
	args=argument_parse()

	chunklistfile=args.chunklist
	fileroot=args.fileroot
	outfile=args.outfile
	outfilemask=args.outmaskfile
	algo=args.algo
	numtrackstr=args.numtracks

	#subjfid=open(subjectlistfile,'r')
	#subjects=[x.strip() for x in subjfid.readlines()]
	#subjfid.close()
	chunklist=np.load(chunklistfile)
	subjects=chunklist["subjects"]

	#subjects=subjects[0:50]
	num_cpu=multiprocessing.cpu_count()
	
	numsubjsplits=int(num_cpu/2)
	numsubj=len(subjects)
	subjsplitidx=np.floor(numsubjsplits*np.arange(numsubj)/numsubj)




	starttime=time.time()
	processes=[]
	for pi in range(numsubjsplits):
		subjlist_split=list(compress(subjects,subjsplitidx==pi))
		outfile1_split='%s_split%02d_endpoint1.npy' % (outfile,pi)
		outfile2_split='%s_split%02d_endpoint2.npy' % (outfile,pi)
		p=multiprocessing.Process(target=save_endpoints,args=(subjlist_split,outfile1_split,outfile2_split))
		processes.append(p)
		p.start()

	for process in processes:
		process.join()

	#print('chunk%05d_xx total time: %.3f seconds' % (ichunk,time.time()-starttime))


	#	if isubj % 10 == 0:
	#		print('%d/%d subjects took %.3f seconds' % (isubj,len(subjects),time.time()-starttime))

	#np.save(outfile,np.append(endpoint1,endpoint2,axis=0))
	#print('Final saving took %.3f seconds' % (time.time()-starttime))

	print('Starting to join %s' % (outfile))
	starttime=time.time()
	endpoint1=[]
	endpoint2=[]
	for pi in range(numsubjsplits):
		subjlist_split=list(compress(subjects,subjsplitidx==pi))
		outfile1_split='%s_split%02d_endpoint1.npy' % (outfile,pi)
		outfile2_split='%s_split%02d_endpoint2.npy' % (outfile,pi)
		endpoint1.append(np.load(outfile1_split))
		endpoint2.append(np.load(outfile2_split))
		os.remove(outfile1_split)
		os.remove(outfile2_split)

	endpointmat=np.vstack((np.vstack(endpoint1),np.vstack(endpoint2)))
	np.save(outfile,endpointmat)
	print('Final join took %.3f seconds' % (time.time()-starttime))

	endpoint1=None
	endpoint2=None

	##################################
	#Now create the endpoints_mask file
	#pretty hacky for now. should clean this up
	print('Creating endpoints_mask')

	starttime=time.time()
	numvoxels=np.prod(chunklist["volshape"])

	#for isubj in range(numsubj):

	num_cpu=multiprocessing.cpu_count()
	multiproc_cores=num_cpu-1
	#multiproc_cores=10
	P=multiprocessing.Pool(multiproc_cores)

	endpointmask_allsubj=P.map(make_endpoint_mask,range(numsubj))
	P.close()


	endpointmask_allsubj=sparse.vstack(endpointmask_allsubj)
	#endpoints for "voxel 0" (corner voxel) are spurious from streamlines that got filtered out during sparsemat creation
	endpointmask_allsubj[:,0]=0
	endpointmask_allsubj.eliminate_zeros()

	print('Creating masks took %.3f seconds' % (time.time()-starttime))

	sparse.save_npz(outfilemask,endpointmask_allsubj,compressed=False)


