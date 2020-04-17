import multiprocessing
import os
import numpy as np
import nibabel as nib
import time
import sys
from scipy.io import loadmat
from scipy import sparse
from nilearn import plotting, image
from scipy import ndimage
from itertools import compress

lesionfile=sys.argv[1]
outputdir=sys.argv[2]
subjectlistfile=sys.argv[3]
sparseroot=sys.argv[4]
refimgfile=sys.argv[5]

if len(sys.argv) > 6 and  sys.argv[6].lower() == 'weighted':
    do_weighted=True
else:
    do_weighted=False

splitvals=None
if len(sys.argv) > 7:
    splitstr=sys.argv[7]
    if '-' in splitstr:
        splitvals=[int(x) for x in splitstr.split('-')]
    elif '+' in splitstr:
        splitvals=[int(x) for x in splitstr.split('+')]
        splitvals[1]=splitvals[0]+splitvals[1]

print('Lesion file: %s' % (lesionfile))
print('Output directory: %s' % (outputdir))
print('Track weighting: ', do_weighted)

starttime=time.time()

refimg=nib.load(refimgfile)

Limg=nib.load(lesionfile)

Ldata=Limg.get_fdata()

if Ldata.shape == (182,218,182):
    #seems correct
    pass
elif Ldata.shape == (181,217,181):
    print('Input was 181x217x181, not the expected 182x218x181. Assuming SPM-based reg and padding end of each dim.')
    Ldata=np.pad(Ldata,(0,1))
else:
    raise('Unexpected size: (%d,%d,%d). Input must be registered to 182x218x182 MNIv6 template (FSL template)', (Ldata.shape))
    
Lmask=Ldata.flatten()>0




subjfid=open(subjectlistfile,'r')
subjects=[x.strip() for x in subjfid.readlines()]
subjfid.close()


#subjects=subjects[:100]

if splitvals is None:
    outputfile=outputdir+'/chaco_allref.npz'
else:
    print('Running on subjects %d to %d' % (splitvals[0],splitvals[1]-1))
    subjects=subjects[splitvals[0]:(splitvals[1])]
    outputfile=outputdir+'/tmpchaco_%05d_%05d.npz' % (splitvals[0],splitvals[1]-1)


os.makedirs(outputdir,exist_ok=True)


algo='ifod2act5Mfsl'
numtrackstr='5M'

subject_sparsefiles=[]
for isubj,subj in enumerate(subjects):
    sparsefile='%s/mnitracks_%s_%s/%s_%s_%s_MNI_sparsemat.mat' % (sparseroot,subj,algo,subj,algo,numtrackstr)
    subject_sparsefiles.append(sparsefile)

def lesion2chaco(infile):
    if do_weighted:
        M=loadmat(infile,variable_names=['A','track_weights','B','Asum_weighted'])
        Asum=M['Asum_weighted'] #.toarray()
        Asum.data = 1/Asum.data.astype(np.float32)
        chacovol=((((Lmask @ M['A'])>0)*M['track_weights']) @ M['B'])*Asum
        print(type(chacovol))
        print(chacovol.dtype)
    else:
        M=loadmat(infile,variable_names=['A','track_weights','B','Asum'])
        Asum=M['Asum'] #.toarray()
        Asum.data = 1/Asum.data.astype(np.float32)

        #this avoids counting a streamline more than once
        #chacovol=sparse.csr_matrix((((Lmask @ M['A'])>0) @ M['B'])*(Asum))
        #chacovol=(((Lmask @ M['A'])>0) @ M['B'])*(Asum)
        return sparse.csr_matrix((((Lmask @ M['A'])>0) @ M['B'])*(Asum.T.toarray()))
        #print(type(chacovol))
        #print(chacovol.dtype)

numsubj=len(subjects)
numsubjsplits=4
subjsplitidx=np.floor(numsubjsplits*np.arange(numsubj)/numsubj)

def lesion2chaco_split(subjsplitidx,whichsplit):
    sparsefiles_split=list(compress(subject_sparsefiles,subjsplitidx==whichsplit))
    chaco_split=[]
    for isp,f in enumerate(sparsefiles_split):
        chaco_split.append(lesion2chaco(f))
    return chaco_split

num_cpu=multiprocessing.cpu_count()
#multiproc_cores=num_cpu-1

#Pool: 4 CPU, 50 subjects took 20 seconds, 100 subjets took 215 seconds (lots of low CPU usage on "top")
#about the same with Process split

#multiproc_cores=4
#P=multiprocessing.Pool(multiproc_cores)
#chaco_allsubj=P.map(lesion2chaco,subject_sparsefiles)
#P.close()

#chaco=lesion2chaco(subject_sparsefiles[0])

#print(chaco)

chaco_allsubj=[lesion2chaco(x) for x in subject_sparsefiles]

sparse.save_npz(outputfile,sparse.vstack(chaco_allsubj),compressed=False)

#chaco_allsubj=[]
#processes=[]
#for pi in range(numsubjsplits):
#	p=multiprocessing.Process(target=lesion2chaco_split,args=(subjsplitidx,pi))
#	processes.append(p)
#	p.start()

#for process in processes:
#	process.join()

#chaco_allsubj=[]
#for i,f in enumerate(subject_sparsefiles):
#    st=time.time()
#    chaco_allsubj.append(lesion2chaco(f))
#    print(time.time()-st)


#print(type(chaco_allsubj))
#print(len(chaco_allsubj))
#print(chaco_allsubj[0])
#print(chaco_allsubj[0].dtype)

print('Final time %.3f seconds' % (time.time()-starttime))

