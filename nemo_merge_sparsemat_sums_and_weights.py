from scipy.io import loadmat
from scipy import sparse
import os
import time
import numpy as np
import sys

chunklistfile=sys.argv[1]
fileroot=sys.argv[2]
outfile_asum=sys.argv[3]
outfile_asum_weighted=sys.argv[4]
outfile_weights=sys.argv[5]

chunklist=np.load(chunklistfile)
subjects=chunklist['subjects']

algo='ifod2act5Mfsl'
numtrackstr='5M'
sparsefiles=[]
for subj in subjects:
	sparsefiles.append('%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr))

#subj x voxels
#Asum is saved as (7M x 1)
starttime=time.time()
Asum_allsubj=sparse.hstack([loadmat(x,variable_names=['Asum'])['Asum'] for x in sparsefiles]).T.tocsr()
sparse.save_npz(outfile_asum,Asum_allsubj,compressed=False)
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
Asum_weighted_allsubj=None
print('Saving %s took %.3f seconds' % (outfile_asum_weighted,time.time()-starttime))

#subj x voxels
weights_allsubj=np.vstack([loadmat(x,variable_names=['track_weights'])['track_weights'].astype(np.float32) for x in sparsefiles])
np.save(outfile_weights,weights_allsubj)
weights_allsubj=None
print('Saving %s took %.3f seconds' % (outfile_weights,time.time()-starttime))
