from scipy.io import loadmat
from scipy import sparse
import os
import time
import numpy as np
import sys
import argparse

def argument_parse():
	parser=argparse.ArgumentParser()

	parser.add_argument('--chunklist',action='store', dest='chunklist', required=True)
	parser.add_argument('--fileroot',action='store', dest='fileroot', required=True)
	parser.add_argument('--endpointfile',action='store', dest='endpointfile', required=True)
	parser.add_argument('--endpointmaskfile',action='store', dest='endpointmaskfile')
	parser.add_argument('--output_weights',action='store', dest='output_weights')
	parser.add_argument('--output_length',action='store', dest='output_length')
	parser.add_argument('--output_asum',action='store', dest='output_asum')
	parser.add_argument('--output_asum_endpoints',action='store', dest='output_asum_endpoints')
	parser.add_argument('--output_asum_weighted',action='store', dest='output_asum_weighted')
	parser.add_argument('--output_asum_weighted_endpoints',action='store', dest='output_asum_weighted_endpoints')
	parser.add_argument('--output_asum_cumulative',action='store', dest='output_asum_cumulative')
	parser.add_argument('--output_asum_weighted_cumulative',action='store', dest='output_asum_weighted_cumulative')
	parser.add_argument('--algo','-a',action='store', dest='algo',default='ifod2act5Mfsl')
	parser.add_argument('--numtracks','-n',action='store', dest='numtracks',default='5M')

	return parser.parse_args()
	
if __name__ == "__main__":
	args=argument_parse()
	chunklistfile=args.chunklist
	fileroot=args.fileroot
	endpointfile=args.endpointfile
	endpointmaskfile=args.endpointmaskfile
	outfile_weights=args.output_weights
	outfile_length=args.output_length
	outfile_asum=args.output_asum
	outfile_asum_endpoints=args.output_asum_endpoints
	outfile_asum_weighted=args.output_asum_weighted
	outfile_asum_weighted_endpoints=args.output_asum_weighted_endpoints
	outfile_asum_cum=args.output_asum_cumulative
	outfile_asum_weighted_cum=args.output_asum_weighted_cumulative
	algo=args.algo
	numtrackstr=args.numtracks
	
	chunklist=np.load(chunklistfile)
	subjects=chunklist['subjects']

	sparsefiles=[]
	for subj in subjects:
		sparsefiles.append('%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr))

	endpointmask=sparse.load_npz(endpointmaskfile)

	#subj x voxels
	#Asum is saved as (7M x 1)
	starttime=time.time()
	Asum_allsubj=sparse.hstack([loadmat(x,variable_names=['Asum'])['Asum'] for x in sparsefiles]).T.tocsr()
	sparse.save_npz(outfile_asum,Asum_allsubj,compressed=False)

	Asum_allsubj=Asum_allsubj.multiply(endpointmask) #save a version masked to include only streamline endpoints
	Asum_allsubj.eliminate_zeros()
	sparse.save_npz(outfile_asum_endpoints,Asum_allsubj,compressed=False)

	Asum_allsubj=None
	print('Saving %s took %.3f seconds' % (outfile_asum,time.time()-starttime))

	#subj x voxels
	#note: for some reason Asum_weighted was saved as (1 x 7M)
	Asum_weighted_allsubj=sparse.vstack([loadmat(x,variable_names=['Asum_weighted'])['Asum_weighted'].astype(np.float32) for x in sparsefiles]).tocsr()
	print(Asum_weighted_allsubj.shape)
	print(100*Asum_weighted_allsubj.nnz/np.prod(Asum_weighted_allsubj.shape))
	print(type(Asum_weighted_allsubj))
	print(Asum_weighted_allsubj.dtype)
	sparse.save_npz(outfile_asum_weighted,Asum_weighted_allsubj,compressed=False)

	Asum_weighted_allsubj=Asum_weighted_allsubj.multiply(endpointmask) #save a version masked to include only streamline endpoints
	Asum_weighted_allsubj.eliminate_zeros()
	sparse.save_npz(outfile_asum_weighted_endpoints,Asum_weighted_allsubj,compressed=False)

	Asum_weighted_allsubj=None
	print('Saving %s took %.3f seconds' % (outfile_asum_weighted,time.time()-starttime))

	#subj x streamlines
	weights_allsubj=np.vstack([loadmat(x,variable_names=['track_weights'])['track_weights'].astype(np.float32) for x in sparsefiles])
	np.save(outfile_weights,weights_allsubj)
	weights_allsubj=None
	print('Saving %s took %.3f seconds' % (outfile_weights,time.time()-starttime))


	#subj x streamlines 
	Alen_allsubj=np.vstack([loadmat(x,variable_names=['A'])['A'].sum(axis=0).astype(np.uint16) for x in sparsefiles])
	np.save(outfile_length,Alen_allsubj)
	Alen_allsubj=None
	print('Saving %s took %.3f seconds' % (outfile_length,time.time()-starttime))


	#subj x voxels
	numsubj=len(subjects)
	numtracks=chunklist['numtracks']
	numvoxels=np.prod(chunklist['volshape'])
	endpointmat=np.load(endpointfile,mmap_mode='r')
	tidx=np.append(np.arange(numtracks),np.arange(numtracks))
	tidx1=np.arange(numtracks)
	tracklengths=np.load(outfile_length,mmap_mode='r')
	trackweights=np.load(outfile_weights,mmap_mode='r')

	w=tracklengths.astype(np.float32)
	Asum_cum=sparse.vstack([sparse.csr_matrix((w[isubj,tidx],(np.zeros(tidx.shape),endpointmat[(isubj,isubj+numsubj),:].flatten())),shape=(1,numvoxels)) for isubj in range(numsubj)]).tolil()
	Asum_cum[:,0]=0
	Asum_cum=Asum_cum.tocsr()
	sparse.save_npz(outfile_asum_cum,Asum_cum,compressed=False)
	Asum_cum=None
	print('Saving %s took %.3f seconds' % (outfile_asum_cum,time.time()-starttime))


	#subj x voxels
	w=(tracklengths*trackweights).astype(np.float32)
	Asum_weighted_cum=sparse.vstack([sparse.csr_matrix((w[isubj,tidx],(np.zeros(tidx.shape),endpointmat[(isubj,isubj+numsubj),:].flatten())),shape=(1,numvoxels)) for isubj in range(numsubj)]).tolil()
	Asum_weighted_cum[:,0]=0
	Asum_weighted_cum=Asum_weighted_cum.tocsr()
	sparse.save_npz(outfile_asum_weighted_cum,Asum_weighted_cum,compressed=False)
	Asum_weighted_cum=None
	print('Saving %s took %.3f seconds' % (outfile_asum_weighted_cum,time.time()-starttime))
