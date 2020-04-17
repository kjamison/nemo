#!/bin/bash

#wr5820_2017_chaco_allref_aal116_style2_glassbrain.png
#wr5827_2015_glassbrain_lesion_orig.png

origdir=$HOME/colossus_shared3/HCP_nemo/origfigs
parcdir=$HOME/colossus_shared3/HCP_nemo/parcfigs
outdir=$HOME/colossus_shared3/HCP_nemo/roistackfigs

mkdir -p $outdir

for i in $origdir/*lesion_orig.png; do
	voximg=${i/_lesion_orig/_chaco_mean}
	b=$(basename ${i/_glassbrain_lesion_orig.png/""})
	aal1=$parcdir/${b}_chaco_allref_aal116_glassbrain.png
	aal2=$parcdir/${b}_chaco_allref_aal116_style2_glassbrain.png
	cc2001=$parcdir/${b}_chaco_allref_cc200_glassbrain.png
	cc2002=$parcdir/${b}_chaco_allref_cc200_style2_glassbrain.png
	cc4001=$parcdir/${b}_chaco_allref_cc400_glassbrain.png
	cc4002=$parcdir/${b}_chaco_allref_cc400_style2_glassbrain.png

	outfile=$outdir/${b}_roistack_glassbrain.png

	convert +append $i $voximg $outdir/${b}_tmp1.png
	convert +append $aal1 $aal2 $outdir/${b}_tmp2.png
	convert +append $cc2001 $cc2002 $outdir/${b}_tmp3.png
	convert +append $cc4001 $cc4002 $outdir/${b}_tmp4.png

	convert -append $outdir/${b}_tmp1.png $outdir/${b}_tmp2.png $outdir/${b}_tmp3.png $outdir/${b}_tmp4.png ${outfile}
	rm $outdir/${b}_tmp?.png
done

