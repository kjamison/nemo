import multiprocessing
import os
from pathlib import Path 
import numpy as np
import nibabel as nib
import time
import sys
from scipy import sparse
from nilearn import plotting, image
from scipy import ndimage
import argparse 
import tempfile

parser=argparse.ArgumentParser(description='Read lesion mask and create voxel-wise ChaCo maps for all reference subjects')

parser.add_argument('--lesion','-l',action='store', dest='lesionfile')
parser.add_argument('--outputbase','-o',action='store', dest='outputbase')
parser.add_argument('--chunklist','-c',action='store', dest='chunklistfile')
parser.add_argument('--chunkdir','-cd',action='store', dest='chunkdir')
parser.add_argument('--refvol','-r',action='store', dest='refimgfile')
parser.add_argument('--endpoints','-e',action='store', dest='endpointfile')
parser.add_argument('--asum','-a',action='store', dest='asumfile')
parser.add_argument('--asum_weighted','-aw',action='store', dest='asumweightedfile')
parser.add_argument('--trackweights','-t',action='store', dest='trackweightfile')
parser.add_argument('--weighted','-w',action='store_true', dest='weighted')
parser.add_argument('--smoothed','-s',action='store_true', dest='smoothed')
parser.add_argument('--smoothfwhm','-sw',default=6, action='store', dest='smoothfwhm')

args=parser.parse_args()

lesionfile=args.lesionfile
outputbase=args.outputbase
chunklistfile=args.chunklistfile
chunkdir=args.chunkdir
refimgfile=args.refimgfile
endpointfile=args.endpointfile
asumfile=args.asumfile
asumweightedfile=args.asumweightedfile
trackweightfile=args.trackweightfile
do_weighted=args.weighted
do_smooth=args.smoothed
smoothing_fwhm=args.smoothfwhm

try:
    smoothing_fwhm=float(smoothing_fwhm)
except ValueError:
    do_smooth=False
    smoothing_fwhm=0.

if smoothing_fwhm <= 0:
    do_smooth=False

#lesionfile=sys.argv[1]
#outputdir=sys.argv[2]
#chunklistfile=sys.argv[3]
#chunkdir=sys.argv[4]
#refimgfile=sys.argv[5]
#endpointfile=sys.argv[6]
#asumfile=sys.argv[7]
#asumweightedfile=sys.argv[8]
#trackweightfile=sys.argv[9]
#if len(sys.argv) > 10 and  sys.argv[10].lower() == 'weighted':
#    do_weighted=True
#else:
#    do_weighted=False


outputdir=Path(outputbase).parent.as_posix()
outputbase_file=Path(outputbase).name

print('Lesion file: %s' % (lesionfile))
print('Output basename: %s' % (outputbase))
print('Track weighting: ', do_weighted)

starttime=time.time()


chunklist=np.load(chunklistfile)
volshape=chunklist['volshape']
chunksize=chunklist['chunksize']
chunkidx_flat=chunklist['chunkidx_flat']
subjects=chunklist['subjects']
numtracks=chunklist['numtracks']
unique_chunks=chunklist['unique_chunks']

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
    raise(Exception('Unexpected size: (%d,%d,%d). Input must be registered to 182x218x182 MNIv6 template (FSL template)' % (Ldata.shape)))
    
Lmask=Ldata.flatten()>0

#wmimg=nib.Nifti1Image(np.reshape(Lmask,Atest['nifti_volshape'][0]),affine=img.affine,header=img.header)
#plotting.view_img(wmimg,bg_img=img,cmap='hot')
#plotting.plot_glass_brain(wmimg,cmap='jet')

chunks_in_lesion=np.unique(chunkidx_flat[Lmask])
print('Total voxels in lesion mask: %d' % (np.sum(Lmask)))
print('Total chunks in lesion mask: %d' % (len(chunks_in_lesion)))
missing_chunks=set(chunks_in_lesion)-set(unique_chunks)
if len(missing_chunks) > 0:
    chunks_to_load=list(set(chunks_in_lesion) - missing_chunks)
    print('Lesion includes %d chunks outside reference white-matter volume' % (len(missing_chunks)))
    print('Total white-matter chunks in lesion mask: %d' % (len(chunks_to_load)))
else:
    chunks_to_load=chunks_in_lesion

totalchunkbytes=np.sum(chunklist['chunkfilesize'][chunks_to_load])
if totalchunkbytes >= 1024*1024*1024:
    print('Total size for all %d chunk files: %.2f GB' % (len(chunks_to_load),totalchunkbytes/(1024*1024*1024)))
else:
    print('Total size for all %d chunk files: %.2f MB' % (len(chunks_to_load),totalchunkbytes/(1024*1024)))

chunkfile_fmt=chunkdir+'/chunk%05d.npz'

numsubj=len(subjects)
numvoxels=chunkidx_flat.size
tidx=np.append(np.arange(numtracks),np.arange(numtracks))

#have to create this before running tempfile.mkdtemp()
os.makedirs(outputdir,exist_ok=True)

#tmpdir=outputbase+'_tmp'
#note: need to set dir explicitly in case we didn't have a "/" or "." in front of output path
#(then it will assume /tmp)
tmpdir=tempfile.mkdtemp(prefix=outputbase_file+'_tmp',dir=outputdir)
tmpchunkfile_fmt=tmpdir+'/tmpsubj_chunk%05d.npz'

#os.makedirs(tmpdir,exist_ok=True)

###########################################################
def save_lesion_chunk(whichchunk):
    subjchunksA=sparse.load_npz(chunkfile_fmt % (whichchunk))
    Lchunk=Lmask[chunkidx_flat==whichchunk]
    chunktrackmask=[]
    for isubj in range(numsubj):
        chunktrackmask.append(sparse.csr_matrix(Lchunk @ subjchunksA[(isubj*chunksize):((isubj+1)*chunksize),:])>0)

    tmpfilename=tmpchunkfile_fmt % (whichchunk)
    sparse.save_npz(tmpfilename,sparse.vstack(chunktrackmask),compressed=False)
###########################################################

num_cpu=multiprocessing.cpu_count()
multiproc_cores=num_cpu-1
P=multiprocessing.Pool(multiproc_cores)

starttime_lesionchunks=time.time()

P.map(save_lesion_chunk,chunks_to_load)
P.close()

print('Track hits for %d chunks took %.3f seconds on %d threads' % (len(chunks_to_load),time.time()-starttime_lesionchunks,multiproc_cores))
#total files for this 376-chunk lesion = 699MB


#now sum up the track hit maps for all chunks
#result = (numsubj x numtracks)
starttime_sum=time.time()

#P=multiprocessing.Pool(multiproc_cores)
#T_allsubj=P.map(sparse.load_npz,[tmpchunkfile_fmt % (whichchunk) for whichchunk in chunks_to_load])
#P.close()
#T_allsubj=sum(T_allsubj)
#print(type(T_allsubj))
#print(T_allsubj.shape)

T_allsubj=None

#this took almost exactly the same amount of time as the Pool version! (350 seconds for big 375chunk lesion)
for ich,whichchunk in enumerate(chunks_to_load):
    tmpfilename=tmpchunkfile_fmt % (whichchunk)
    Tchunk=sparse.load_npz(tmpfilename)
    if T_allsubj is None:
        T_allsubj=Tchunk
    else:
        T_allsubj+=Tchunk
    os.remove(tmpfilename)
print('Merging track hits from %d chunks took %.3f seconds' % (len(chunks_to_load),time.time()-starttime_sum))


##############
#part 2
if do_weighted:
    Asum=sparse.load_npz(asumweightedfile)
    trackweights=np.load(trackweightfile,mmap_mode='r')
else:
    Asum=sparse.load_npz(asumfile)
    trackweights=None

#need this in the denominator
#also make sure the non-weighted Asum (int32) gets cast as float32
#(otherwise it creates a float64)
Asum.data=1/Asum.data.astype(np.float32)

endpointmat=np.load(endpointfile,mmap_mode='r')

###########################################################
def map_to_endpoints(isubj):
    endpt=endpointmat[(isubj,isubj+numsubj),:].flatten()
    B=sparse.csr_matrix((np.ones(tidx.shape,dtype=bool),(tidx,endpt)),shape=(numtracks,numvoxels))
    if do_weighted:
        #tmpmat=(T_allsubj[isubj,:]>0)
        #tw=trackweights[isubj,:]
        #print('left: ',tmpmat.shape,type(tmpmat))
        #print('trackweight: ',tw.shape, type(tw))
        #tmp2=tmpmat.multiply(tw)
        #print('broadcast: ', tmp2.shape, type(tmp2))
        
        #D=(T_allsubj[isubj,:]>0).multiply(trackweights[isubj,:]) @ B
        #print('type(D): ',type(D))
        #print('D.dtype: ', D.dtype)
        #print('D.nnz: ', D.nnz)

        #chacovol=D.multiply(Asum[isubj,:])
        #print('type(chacovol): ',type(chacovol))
        #print('chacovol.dtype: ', chacovol.dtype)
        #print('chacovol.nnz: ', chacovol.nnz)

        #chacovol=sparse.csr_matrix(((T_allsubj[isubj,:]>0).multiply(trackweights[isubj,:]) @ B)*Asum[isubj,:],dtype=np.float32)
        chacovol=((T_allsubj[isubj,:]>0).multiply(trackweights[isubj,:]) @ B).multiply(Asum[isubj,:])
    else:
        #chacovol=sparse.csr_matrix(((T_allsubj[isubj,:]>0) @ B)/Asum[isubj,:],dtype=np.float32)
        chacovol=((T_allsubj[isubj,:]>0) @ B).multiply(Asum[isubj,:])

    
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    sparse.save_npz(chacofile_subj,chacovol,compressed=False)
###########################################################

#Now multiply with B mat to go from tracks->endpoints
#result = (numsubj x numvoxels)
starttime_endpoints=time.time()



#multiproc_cores=1
P=multiprocessing.Pool(multiproc_cores)
P.map(map_to_endpoints, range(numsubj))
P.close()

endpointmat=None

print('Mapping to endpoints and ChaCo took %.3f seconds on %d threads' % (time.time()-starttime_endpoints,multiproc_cores))

voxmm=1
fwhm=smoothing_fwhm
smoothvol=lambda x: ndimage.gaussian_filter(np.reshape(np.array(x.todense()),volshape),sigma=fwhm/2.35482/voxmm)

#note: the non-sparse version of this runs in ~20 seconds on 16 core, but takes up 28MB*420=12GB temporarily
def smoothfun(infile_outfile):
    outsmooth=sparse.csr_matrix(smoothvol(sparse.load_npz(infile_outfile[0])).flatten())
    outsmooth.eliminate_zeros()
    return outsmooth
    #sparse.save_npz(infile_outfile[1],outsmooth,compressed=False)
    #np.save(infile_outfile[1],smoothvol(sparse.load_npz(infile_outfile[0])))


if do_smooth:
    print('Smoothing individual ChaCo volumes at FWHM=%.2fmm (Just to generate a pretty mean image)' % (fwhm))
    smooth_infile_list=[tmpdir+'/chacovol_subj%05d.npz' % (isubj) for isubj in range(numsubj)]
    smooth_outfile_list=[tmpdir+'/chacovol_subj%05d_smoothed.npz' % (isubj) for isubj in range(numsubj)]
    smoothstart=time.time()
    P=multiprocessing.Pool(multiproc_cores)
    chaco_smooth=P.map(smoothfun, zip(smooth_infile_list,smooth_outfile_list))
    P.close()
    chaco_smooth=sum(chaco_smooth)/numsubj
    #print('Smooth.0 took %.3f seconds' % (time.time()-smoothstart))

    
    #chaco_smooth=None
    #for f in smooth_outfile_list:
    #    if chaco_smooth is None:
    #        #chaco_smooth=np.load(f)
    #        chaco_smooth=sparse.load_npz(f)
    #    else:
    #        #chaco_smooth+=np.load(f)
    #        chaco_smooth+=sparse.load_npz(f)
    #    os.remove(f)
    #chaco_smooth/=numsubj

    print('Smoothing took %.3f seconds' % (time.time()-smoothstart))

    #imgsmooth=nib.Nifti1Image(chaco_smooth,affine=refimg.affine, header=refimg.header)
    imgsmooth=nib.Nifti1Image(np.reshape(np.array(chaco_smooth.todense()),volshape),affine=refimg.affine, header=refimg.header)
    imgfile_smooth=outputbase+'_glassbrain_chaco_smoothmean_%gmm.png' % (fwhm)
    plotting.plot_glass_brain(imgsmooth,output_file=imgfile_smooth,colorbar=True)
    nib.save(imgsmooth,outputbase+'_chaco_smoothmean_%gmm.nii.gz' % (fwhm))

chaco_allsubj=[]
starttime_merge_final=time.time()
for isubj in range(numsubj):
    chacofile_subj=tmpdir+'/chacovol_subj%05d.npz' % (isubj)
    chaco_allsubj.append(sparse.load_npz(chacofile_subj))
    os.remove(chacofile_subj)
os.rmdir(tmpdir)
print('Loading final chaco maps took %.3f seconds' % (time.time()-starttime_merge_final))


chaco_allsubj=sparse.vstack(chaco_allsubj)
sparse.save_npz(outputbase+'_chaco_allref.npz',chaco_allsubj,compressed=False)

chacomean=np.array(np.mean(chaco_allsubj,axis=0))
imgchaco=nib.Nifti1Image(np.reshape(chacomean,volshape),affine=refimg.affine, header=refimg.header)
imgfile_mean=outputbase+'_glassbrain_chaco_mean.png'
plotting.plot_glass_brain(imgchaco,output_file=imgfile_mean,colorbar=True)
nib.save(imgchaco,outputbase+'_chaco_mean.nii.gz')

imglesion_mni=nib.Nifti1Image(Ldata>0,affine=refimg.affine, header=refimg.header)
imgfile_lesion=outputbase+'_glassbrain_lesion_orig.png'
plotting.plot_glass_brain(imglesion_mni,output_file=imgfile_lesion,cmap='jet',colorbar=True)

print('NeMo took a total of %.3f seconds for %s' % (time.time()-starttime,lesionfile))

