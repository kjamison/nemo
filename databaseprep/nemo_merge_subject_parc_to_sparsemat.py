import sys
import numpy as np
from scipy import sparse
import scipy.stats
import tempfile
from pathlib import Path 
import subprocess
import multiprocessing
import boto3
import nibabel as nib
import nibabel.processing
import time
import os
import pickle

chunklistfile=sys.argv[1]
parcname=sys.argv[2]
reffile=sys.argv[3]
outputbase=sys.argv[4]
numdil=0
if len(sys.argv) > 5:
    numdil=round(float(sys.argv[5]))
tmpdir=None
if len(sys.argv) > 6:
    tmpdir=sys.argv[6]

outputdir=Path(outputbase).parent.as_posix()
outputbase_file=Path(outputbase).name
if tmpdir is None:
    tmpdir=tempfile.mkdtemp(prefix=outputbase_file+'_tmp',dir=outputdir)

chunklist=np.load(chunklistfile)
subjects=chunklist['subjects']


refimg=nib.load(reffile)

#parcname=fs86, fs86_sgmfix, fs111cereb, fs111cereb_sgmfix

#each parcname and dilation takes 5-15min (shorter=no dilation)
#for p in fs86 fs111cereb fs86_sgmfix fs111cereb_sgmfix; do outd=subjparc; mkdir -p $outd; tmpd=parctemp_${p}; mkdir -p $tmpd; for d in 0 1 2 3; do python nemo_merge_subject_parc_to_sparsemat.py nemo2/nemo_chunklist.npz ${p} nemo2/MNI152_T1_1mm_brain.nii.gz $outd/${p}_dil${d}_allsubj $d $tmpd; aws s3 sync $outd/ s3://kuceyeski-wcm-web-upload/nemo_atlases/ --exclude "*.pkl"; done; done; klaws stop

s3paths=["s3://kuceyeski-wcm-temp/kwj2001/mrtrix_tckgen_%s/%s_MNI.nii.gz" % (s,parcname) for s in subjects]

fsldir="/home/ubuntu/fsl"

dilarg=["-dilD"] * numdil

print(dilarg)

s3_client = None
def s3initialize():
    global s3_client
    s3_client = boto3.client('s3')

def get_flattened_1mm(s3name):
    s3bucket=s3name.replace("s3://","").split("/")[0]
    s3key="/".join(s3name.replace("s3://","").split("/")[1:])
    filename=tmpdir+"/"+s3key.replace("/","_")
    if not Path(filename).is_file():
        s3_client.download_file(s3bucket,s3key,filename)
    filename1mm=filename.replace(".nii.gz","_1mm.nii.gz")
    if not Path(filename1mm).is_file():
        subprocess.Popen([fsldir+"/bin/applywarp","-i",filename,"-r",reffile,"-o",filename1mm,'--interp=nn'],env=dict(os.environ, FSLOUTPUTTYPE="NIFTI_GZ")).wait()
    #dilate the ROIs twice just to make sure they catch all (most?) of the streamline endpoints
    if numdil > 0:
        if(numdil==1):
            dilprevfile=filename1mm
        else:
            dilprevfile=filename1mm.replace("_1mm.nii.gz","_1mm_dil%d.nii.gz" % (numdil-1))
        dilfile=filename1mm.replace("_1mm.nii.gz","_1mm_dil%d.nii.gz" % (numdil))
        
        if Path(dilprevfile).is_file():
            #if previous dilation file is found, just dilate that one time
            subprocess.Popen([fsldir+"/bin/fslmaths",dilprevfile,'-dilD',dilfile],env=dict(os.environ, FSLOUTPUTTYPE="NIFTI_GZ")).wait()
        else:
            #perform all dilations
            subprocess.Popen([fsldir+"/bin/fslmaths",filename1mm]+dilarg+[dilfile],env=dict(os.environ, FSLOUTPUTTYPE="NIFTI_GZ")).wait()
    else:
        dilfile=filename1mm
    
        #subprocess.Popen([fsldir+"/bin/fslmaths",filename1mm]+dilarg+[filename1mm],env=dict(os.environ, FSLOUTPUTTYPE="NIFTI_GZ")).wait()
    #newvals=sparse.csr_matrix(nib.load(filename1mm).get_fdata().flatten(),dtype=np.uint16)
    
    newvals=sparse.csr_matrix(nib.load(dilfile).get_fdata().flatten(),dtype=np.uint16)
    
    #newvals=sparse.csr_matrix(nib.processing.resample_from_to(nib.load(filename), refimg, order=0).get_fdata().flatten(),dtype=np.uint16)
    return newvals

s3initialize()
s3_client.download_file("kuceyeski-wcm-temp","kwj2001/fsl/bin/applywarp",fsldir+"/bin/applywarp")
s3_client.download_file("kuceyeski-wcm-temp","kwj2001/fsl/bin/fslmaths",fsldir+"/bin/fslmaths")
subprocess.Popen(["chmod","+x","/home/ubuntu/fsl/bin/applywarp"])
subprocess.Popen(["chmod","+x","/home/ubuntu/fsl/bin/fslmaths"])
starttime=time.time()

print('Converting %d subject %s to sparsemat ' % (len(subjects),parcname), end='', flush=True)
num_cpu=multiprocessing.cpu_count()
multiproc_cores=num_cpu-1
P=multiprocessing.Pool(multiproc_cores, s3initialize)
Psparse_allsubj=sparse.vstack(P.map(get_flattened_1mm,s3paths))
P.close()

print('took %.3f seconds' % (time.time()-starttime))

sparse.save_npz(outputbase+".npz",Psparse_allsubj,compressed=False)

mode,counts=scipy.stats.mode(Psparse_allsubj.toarray(),axis=0)
imgmode=nib.Nifti1Image(np.reshape(mode,refimg.shape),affine=refimg.affine, header=refimg.header)
nib.save(imgmode,outputbase+"_mode.nii.gz")

print('Creating mode of %s took %.3f seconds' % (parcname,time.time()-starttime))


def get_sparse_transform(isubj):
    Pdata=Psparse_allsubj[isubj,:].toarray().flatten()
    numvoxels=Pdata.size
    pmaskidx=np.where(Pdata!=0)[0]
    uroi, uidx=np.unique(Pdata[Pdata!=0],return_inverse=True)
    numroi=len(uroi)
    return sparse.csc_matrix((np.ones(pmaskidx.size),(pmaskidx,uidx)),shape=(numvoxels,numroi),dtype=np.float32)
    
print('Converting %d subject %s to transform ' % (len(subjects),parcname), end='', flush=True)

P=multiprocessing.Pool(multiproc_cores)
Psparse_allsubj_list=P.map(get_sparse_transform,range(len(subjects)))
P.close()

print('took %.3f seconds' % (time.time()-starttime))

pickle.dump(Psparse_allsubj_list,open(outputbase+".pkl","wb"))
