#!/bin/bash


subject=$1
algostr=$2

set -e
set -x

if [ $USER = "ubuntu" ]; then
	studydir=/home/ubuntu/mniwarp
	scriptdir=/home/ubuntu
else
	studydir=$HOME/colossus_shared/HCP/mniwarptest
	scriptdir=.
fi
#inputdir=$studydir/input_mrtrix_${subject}
outputdir=$studydir/mnitracks_${subject}_${algostr}
#outputdir=$studydir/output_mrtrix_${subject}

if [[ "$subject" == *_Retest ]]; then
	hcps3dir=HCP_Retest
	hcps3subject=${subject/_Retest/""}
else
	hcps3dir=HCP_1200
	hcps3subject=${subject}
fi

mkdir -p ${outputdir}


cd $outputdir

#algostr=sdstream
#algostr=ifod2
#algostr=ifod2act5Mfsl

if [ "$algostr" = "sdstream" ]; then
	algodirstr=""
else
	algodirstr="_${algostr}"
fi

numtracks=5M
tckfile=CSD_${algostr}_${numtracks}.tck
siftfile=${tckfile/.tck/_sift2.txt}
aws s3 sync s3://kuceyeski-wcm-temp/kwj2001/mrtrix_tckgen_${subject}${algodirstr}/ ./ --exclude "*" --include "${tckfile}" --include "${siftfile}" --include "nodif_brain_mask.nii.gz"

aws --profile hcp s3 sync s3://hcp-openaccess/${hcps3dir}/${hcps3subject}/MNINonLinear/xfms/ ./ --exclude "*" --include "standard2acpc_dc.nii.gz" --include "acpc_dc2standard.nii.gz"

#aws --profile hcp s3 sync s3://hcp-openaccess/${hcps3dir}/${hcps3subject}/MNINonLinear/ ./ --exclude "*" --include "T1w_restore.2.nii.gz"

#aws --profile hcp s3 sync s3://hcp-openaccess/${hcps3dir}/${hcps3subject}/MNINonLinear/ ./ --exclude "*" --include "T1w_restore.nii.gz"

if [ $USER = "ubuntu" ]; then
	aws s3 cp s3://kuceyeski-wcm-temp/kwj2001/fsl/data/standard/MNI152_T1_1mm_brain_mask.nii.gz ./
	mnitarget=MNI152_T1_1mm_brain_mask.nii.gz
else
	#mnitarget=T1w_restore.2.nii.gz
	mnitarget=$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz
fi

regimg=nodif_brain_mask.nii.gz
threadarg="-nthreads 0"
#took 3m52s with nthread 1 on AWS (cpu usage seemed to stick around 130% ??)
#(~1min of total is s3 sync which goes up to 165% CPU)
#took 3m48s with nthread 0 on AWS (cpu usage maxed at 100% for non-s3 sync mrtrix parts)

lengthfile=${tckfile/.tck/_tracklength.txt}
tckstats -dump ${lengthfile} ${tckfile} ${threadarg} -force

#Don't need to generate this test output anymore:
#tdifile=${tckfile/.tck/_tdi.nii.gz}
#tdifileMNI=${tdifile/.nii.gz/_MNI.nii.gz}
#tckmap ${tckfile} ${tdifile} -template ${regimg} ${threadarg} -force
#applywarp -i ${tdifile} -r ${mnitarget} -w acpc_dc2standard.nii.gz --interp=trilinear -o ${tdifileMNI}

#fail: warpconvert acpc_dc2standard.nii.gz displacement2deformation acpc2mni_mrtrix.nii.gz -force
#fail: mrtransform ${tdifile} ${tdifile/.nii.gz/_MNImrtrix.nii.gz} -warp acpc2mni_mrtrix.nii.gz -force
#warpconvert standard2acpc_dc.nii.gz displacement2deformation warp_MNI

#mrconvert acpc_dc2standard.nii.gz tmp-[].nii -force
#mv tmp-0.nii x.nii
#mrcalc x.nii -neg 1.25 -mult tmp-0.nii -force
#warpconvert tmp-[].nii displacement2deformation acpc2mni_mrtrix_flipscale.nii -force
#rm x.nii tmp-?.nii

#mrtransform ${tdifile} ${tdifile/.nii.gz/_MNImrtrixflipscale.nii.gz} -warp acpc2mni_mrtrix_flipscale.nii -force

mrconvert acpc_dc2standard.nii.gz tmp-[].nii -force ${threadarg}
mv tmp-0.nii x.nii
mrcalc x.nii -neg tmp-0.nii -force ${threadarg}
warpconvert tmp-[].nii displacement2deformation acpc2mni_mrtrix_flip.nii.gz -force ${threadarg}
rm x.nii tmp-?.nii


#Don't need this test output anymore
#mrtransform ${tdifile} ${tdifile/.nii.gz/_MNImrtrixflip.nii.gz} -warp acpc2mni_mrtrix_flip.nii.gz -force


mrconvert standard2acpc_dc.nii.gz tmp-[].nii -force ${threadarg}
mv tmp-0.nii x.nii
mrcalc x.nii -neg tmp-0.nii -force ${threadarg}
warpconvert tmp-[].nii displacement2deformation mni2acpc_mrtrix_flip.nii.gz -force ${threadarg}
rm x.nii tmp-?.nii

tckfileMNI=${tckfile/.tck/_MNI.tck}
tdifileMNInative=${tckfile/.tck/_MNI_tdi.nii.gz}
tcktransform ${tckfile} mni2acpc_mrtrix_flip.nii.gz ${tckfileMNI} -force ${threadarg}
tckmap ${tckfileMNI} ${tdifileMNInative} -template ${mnitarget} ${threadarg} -force ${threadarg}
fslmaths ${mnitarget} -mul 0 -add ${tdifileMNInative} ${tdifileMNInative}

#python ${scriptdir}/convert_mni_tck_to_sparsemat.py ${tckfile/.tck/""} ${mnitarget} ${tckfile/.tck/_MNI_sparsemat.mat}

#summary:
#1. generate original acpc-space _tdi.nii.gz file
#2. FSL/HCP warp _tdi.nii.gz to _tdi_MNI2.nii.gz with acpc_dc2standard.nii.gz (looks good)

#these two steps are bad:
#3. convert acpc_dc2standard to mrtrix format acpc2mni_mrtrix (no changes)
#4. MRTRIX warp _tdi.nii.gz to _tdi_MNImrtrix.nii.gz (looks squished)

#5. convert acpc_dc2standard to mrtrix format acpc2mni_mrtrix_flip WITH X-AXIS FLIP
#6. MRTRIX warp _tdi.nii.gz to _tdi_MNImrtrixflip.nii.gz with new transform (looks good!)

#7. convert standard2acpc_dc to mrtrix format mni2acpc_mrtrix_flip WITH X-AXIS FLIP
#8. MRTRIX transform .tck file and make new _MNI_tdi.nii.gz file (looked good!)
