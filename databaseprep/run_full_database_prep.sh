#!/bin/bash

set -e
set -x

#algo=ifod2act5Mfsl
#algostr=$algo

algo=sdstream
algostr=""

nemodata_s3root=s3://kuceyeski-wcm-temp/kwj2001/nemo2
mnitracks_s3root=s3://kuceyeski-wcm-temp/kwj2001/mnitracks

subjectfile=subjects_unrelated420_scfc.txt
refvol=MNI152_T1_1mm_brain.nii.gz
numtracks=5M

mnitracksdir=${HOME}/nemo_mnitracks
mkdir -p ${mnitracksdir}

aws s3 cp s3://kuceyeski-wcm-temp/kwj2001/fsl/data/standard/MNI152_T1_1mm_brain_mask.nii.gz ${refvol}
aws s3 cp s3://kuceyeski-wcm-temp/kwj2001/${subjectfile} ${subjectfile}

#note: this step is meant to be run in parallel on AWS, separately from the rest of the database prep
#this loop is just written to show how it should be called
#for subj in $(cat ${subjectfile}); do
    ## option 1: this runs run_warp_tck_to_mni.sh and nemo_convert_mni_tck_to_sparsemat.py and uploads outputs to S3
    #nemo_run_warp_and_sparsemat.sh $subj $algo
    
    ## option 2: run each of those scripts and keep them locally
    #subjdir=${mnitracksdir}/mnitracks_${subj}_${algo}
    #bash run_warp_tck_to_mni.sh $subj $algo
    #python ${scriptdir}/nemo_convert_mni_tck_to_sparsemat.py ${subjdir}/CSD_${algo}_${numtracks} ${refvol} ${subjdir}/${subj}_${algo}_${numtracks}_MNI_sparsemat.mat
#done

####################
nemodir=$HOME/nemo2

chunklistfile=$nemodir/nemo_${algo}_chunklist.npz

endpointfile=$nemodir/nemo_${algo}_endpoints.npy
endpointmaskfile=$nemodir/nemo_${algo}_endpoints_mask.npz

chunkdir=$nemodir/chunkfiles_${algo}

asumfile=$nemodir/nemo_${algo}_Asum.npz
asumfile_endpoints=$nemodir/nemo_${algo}_Asum_endpoints.npz
asumfile_weighted=$nemodir/nemo_${algo}_Asum_weighted.npz
asumfile_weighted_endpoints=$nemodir/nemo_${algo}_Asum_weighted_endpoints.npz
asumfile_cumulative=$nemodir/nemo_${algo}_Asum_cumulative.npz
asumfile_weighted_cumulative=$nemodir/nemo_${algo}_Asum_weighted_cumulative.npz
trackweightfile=$nemodir/nemo_${algo}_siftweights.npy
tracklengthfile=$nemodir/nemo_${algo}_tracklengths.npy

if [ a = b ]; then
####################
#takes ~90 min to sync the full 600GB mnitracks S3 folder to EC2 instance
mkdir -p $nemodir

numcpu=$(python -c 'import multiprocessing; print(multiprocessing.cpu_count())')
cat ${subjectfile} | while read s; do echo aws s3 sync ${mnitracks_s3root}/ ${mnitracksdir} --exclude "\*" --include "\*/${s}_${algo}_\*_sparsemat.mat"; done | parallel -j $((numcpu/2))
#aws s3 sync ${mnitracks_s3root}/ ${mnitracksdir} --exclude "*" --include "*_${algo}_*_sparsemat.mat"

####################
python nemo_save_chunklist.py --subjects ${subjectfile} --fileroot ${mnitracksdir} --output ${chunklistfile} --ref ${refvol} --algo ${algo} --numtracks ${numtracks}
####################

####################
python nemo_save_endpoints.py --chunklist ${chunklistfile} --fileroot ${mnitracksdir} --output ${endpointfile} --outputmask ${endpointmaskfile} --algo ${algo} --numtracks ${numtracks}
####################
fi

####################
mkdir -p $chunkdir
python nemo_save_subjchunks.py --chunklist ${chunklistfile} --fileroot ${mnitracksdir} --outputdir ${chunkdir} --algo ${algo} --numtracks ${numtracks}
####################


####################
python nemo_merge_sparsemat_sums_and_weights.py --chunklist ${chunklistfile} --fileroot ${mnitracksdir} \
    --endpointfile ${endpointfile} --endpointmaskfile ${endpointmaskfile} --output_weights ${trackweightfile} --output_length ${tracklengthfile} \
    --output_asum ${asumfile} --output_asum_endpoints ${asumfile_endpoints} --output_asum_weighted ${asumfile_weighted} \
    --output_asum_weighted_endpoints ${asumfile_weighted_endpoints} --output_asum_cumulative ${asumfile_cumulative} \
    --output_asum_weighted_cumulative ${asumfile_weighted_cumulative} --algo ${algo} --numtracks ${numtracks}
####################

#######################
#Save a couple of volumes to visualize streamlines and endpoints
for f in ${asumfile} ${asumfile_endpoints} ${asumfile_weighted} ${asumfile_weighted_endpoints} ${asumfile_cumulative} ${asumfile_weighted_cumulative}; do
    python -c 'import numpy as np; from scipy import sparse; import nibabel as nib; A=sparse.load_npz("'${f}'"); Vref=nib.load("'${refvol}'"); Vnew=nib.Nifti1Image(np.reshape(np.array(np.sum(A,axis=0)),Vref.shape),affine=Vref.affine,header=Vref.header); nib.save(Vnew,"'${f/.np?/.nii.gz}'")'
done

#######################

#sync final 700GB nemo files + chunk files
rm -rf ${chunkdir}/chunkdir*
aws s3 sync $nemodir ${nemodata_s3root}