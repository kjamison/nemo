import numpy as np
#from scipy import sparse
from scipy.io import loadmat
import sys
import time
import nibabel as nib

subjectlistfile=sys.argv[1]
fileroot=sys.argv[2]
outfile=sys.argv[3]
refvolfile=None
if len(sys.argv)>4:
	refvolfile=sys.argv[4]

subjfid=open(subjectlistfile,'r')
subjects=[x.strip() for x in subjfid.readlines()]
subjfid.close()

algo='ifod2act5Mfsl'
numtrackstr='5M'

numsubj=len(subjects)

#############
if refvolfile:
    refimg=nib.load(refvolfile)
    volshape=refimg.shape
else:
    volshape=np.array([182,218,182])
    
chunkvoxsize=10
chunksize=chunkvoxsize*chunkvoxsize*chunkvoxsize
chunkvec_x=np.int32(np.floor(np.arange(volshape[0])/chunkvoxsize))
chunkvec_y=np.int32(np.floor(np.arange(volshape[1])/chunkvoxsize))
chunkvec_z=np.int32(np.floor(np.arange(volshape[2])/chunkvoxsize))

chunkvec_size=(chunkvec_x[-1]+1, chunkvec_y[-1]+1, chunkvec_z[-1]+1)
                                      
chunky,chunkx,chunkz=np.meshgrid(chunkvec_y,chunkvec_x,chunkvec_z)

#a volsize 3D array where each entry is a 0-numchunks index
chunkidx=chunkz + chunky*chunkvec_size[0] + chunkx*chunkvec_size[0]*chunkvec_size[1]
#a voxidx x 1 array where chunkidx_flat(voxidx)=chunk index
chunkidx_flat=chunkidx.flatten()
numchunks=np.max(chunkidx)+1

#############
starttime=time.time()
Asum=[]
subject_sparsefiles=[]
numtracks=None
for isubj,subj in enumerate(subjects):
	sparsefile='%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (fileroot,subj,algo,subj,algo,numtrackstr)
	subject_sparsefiles.append(sparsefile)
	Atmp=loadmat(sparsefile,variable_names=['Asum'])['Asum']
	if isubj == 0:
		Asum=Atmp
		print(Asum.shape)
	else:
		Asum+=Atmp
		
	if numtracks is None:
	    numtracks=loadmat(sparsefile,variable_names=['track_weights'])['track_weights'].size
	    
	if isubj > 0 and isubj % 5 == 0:
		print('Loading %d/%d took %.3f seconds' % (isubj,len(subjects),time.time()-starttime))

Asum=Asum.todense().squeeze()
Amask=Asum>0
unique_chunks=np.unique(chunkidx_flat[Amask])
np.savez(outfile,Asum=Asum, Amask=Amask, subjects=subjects, subject_sparsefiles=subject_sparsefiles, \
	volshape=volshape, chunkvoxsize=chunkvoxsize, chunksize=chunksize, chunkidx=chunkidx, \
	chunkidx_flat=chunkidx_flat, numchunks=numchunks, unique_chunks=unique_chunks, num_unique_chunks=len(unique_chunks), \
	numtracks=numtracks)

