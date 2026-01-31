import numpy as np
import nibabel as nib
from scipy import sparse
from scipy.io import loadmat
from nilearn import plotting
from pathlib import Path 
import sys
import multiprocessing

parcelfile=sys.argv[1]
outputdir=sys.argv[2]
outputsuffix=sys.argv[3]
matfiles=sys.argv[4:]

#parcelfile='/home/kwj2001/colossus_shared/atlases/aal_for_SPM12/AAL116_MNI152_1mm_182x218x182.nii.gz'
#roi_chaco_file='/home/kwj2001/colossus_shared3/HCP_nemo/nemo_output/wr2609_2013_chaco_allref_aal116_style2.mat'

#parcelfile='/home/kwj2001/colossus_shared/atlases/cc400_new1mm.nii.gz'
#roi_chaco_file='/home/kwj2001/colossus_shared3/HCP_nemo/nemo_output/wr2609_2013_chaco_allref_cc400_style2.mat'

parcelimg=nib.load(parcelfile)

Pdata=np.round(parcelimg.get_fdata()).flatten()
volshape=parcelimg.header.get_data_shape()
numvoxels=Pdata.size
pmaskidx=np.where(Pdata!=0)[0]
uroi, uidx=np.unique(Pdata[Pdata!=0],return_inverse=True)
numroi=len(uroi)
Psparse=sparse.csr_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)

def savefigure(m):
    imgfilename=outputdir+'/'+Path(m).name.replace('.mat',outputsuffix)
    roi_chaco_allref=loadmat(m)['roi_chaco_allref']

    if roi_chaco_allref.shape[1] != numroi:
        print('Parcellation has %d labels, but input file is [subjects x %d]: %s' % (numroi,roi_chaco_allref.shape[1],m))
        exit(1)

    roi_chaco_mean=np.mean(roi_chaco_allref,axis=0)
    roivol_chaco_allref=Psparse @ roi_chaco_mean.T

    imgchaco=nib.Nifti1Image(np.reshape(roivol_chaco_allref,volshape),affine=parcelimg.affine, header=parcelimg.header)

    plotting.plot_glass_brain(imgchaco,output_file=imgfilename,colorbar=True,threshold=0)

multiproc_cores=15
P=multiprocessing.Pool(multiproc_cores)
P.map(savefigure, matfiles)
P.close()

