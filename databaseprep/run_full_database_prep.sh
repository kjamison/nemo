#!/bin/bash

algo=ifod2act5Mfsl
algostr=$algo

#algo=sdstream
#algostr=""

nemodata_s3root=s3://kuceyeski-wcm-temp/kwj2001/nemo2
mnitracks_s3root=s3://kuceyeski-wcm-temp/kwj2001/mnitracks

subjectfile=subjects_unrelated420_scfc.txt
refvol=MNI152_T1_1mm_brain.nii.gz
numtracks=5M

mnitracksdir=${HOME}/nemo_mnitracks
mkdir -p ${mnitracksdir}

#note: this step is meant to be run in parallel on AWS, separately from the rest of the database prep
#this loop is just written to show how it should be called
for subj in $(cat ${subjectfile}); do
    ## option 1: this runs run_warp_tck_to_mni.sh and nemo_convert_mni_tck_to_sparsemat.py and uploads outputs to S3
    #nemo_run_warp_and_sparsemat.sh $subj $algo
    
    ## option 2: run each of those scripts and keep them locally
    #subjdir=${mnitracksdir}/mnitracks_${subj}_${algo}
    #bash run_warp_tck_to_mni.sh $subj $algo
    #python ${scriptdir}/nemo_convert_mni_tck_to_sparsemat.py ${subjdir}/CSD_${algo}_${numtracks} ${refvol} ${subjdir}/${subj}_${algo}_${numtracks}_MNI_sparsemat.mat
done

####################
nemodir=$HOME/nemo2

chunklistfile=$nemodir/nemo_chunklist.npz

endpointfile=$nemodir/nemo_endpoints.npy
endpointmaskfile=$nemodir/nemo_endpoints_mask.npz

chunkdir=$nemodir/chunkfiles

asumfile=$nemodir/nemo_Asum.npz
asumfile_endpoints=$nemodir/nemo_Asum_endpoints.npz
asumfile_weighted=$nemodir/nemo_Asum_weighted.npz
asumfile_weighted_endpoints=$nemodir/nemo_Asum_weighted_endpoints.npz
asumfile_cumulative=$nemodir/nemo_Asum_cumulative.npz
asumfile_weighted_cumulative=$nemodir/nemo_Asum_weighted_cumulative.npz
trackweightfile=$nemodir/nemo_siftweights.npy
tracklengthfile=$nemodir/nemo_tracklengths.npy


####################
#takes ~90 min to sync the full 600GB mnitracks S3 folder to EC2 instance
mkdir -p $nemodir
aws s3 sync ${mnitracks_s3root}/ ${mnitracksdir}
python nemo_save_chunklist.py ${subjectfile} ${mnitracksdir} ${chunklistfile} ${refvol}
####################


####################
python nemo_save_endpoints.py ${chunklistfile} ${mnitracksdir} ${endpointfile} ${endpointmaskfile}
####################


####################
mkdir -p $chunkdir
python nemo_save_subjchunks.py ${chunklistfile} ${mnitracksdir} ${chunkdir}
####################


####################
nemo_merge_sparsemat_sums_and_weights.py ${chunklistfile} ${mnitracksdir} ${endpointfile} ${endpointmaskfile} ${trackweightfile} ${tracklengthfile} \
    ${asumfile} ${asumfile_endpoints} ${asumfile_weighted} ${asumfile_weighted_endpoints} ${asumfile_cumulative} ${asumfile_weighted_cumulative}
####################

#sync final 700GB nemo files + chunk files
aws s3 sync $nemodir ${nemodata_s3root}