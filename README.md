# NeMo 2.0 - Network Modification Tool

Predict brain network disruption from a lesion mask. Original concept described in [Kuceyeski 2013](https://dx.doi.org/10.1089%2Fbrain.2013.0147).

## Workflow overview

The general workflow for this tool consists of a database generation stage and a lesion disconnectivity stage:

1. Tractography database generation: [databaseprep/](databaseprep/)
    1. Compute whole-brain tractogram streamlines for 420 unrelated healthy subjects from the [Human Connectome Project](http://www.humanconnectome.org) (See [hcp_subjects_unrelated420_scfc.txt](hcp_subjects_unrelated420_scfc.txt) for list)
    2. Nonlinearly warp streamlines into a common reference space (MNI152 v6, eg: <code>$FSLDIR/data/standard/MNI152_T1_1mm.nii.gz</code>, or [website/atlases/MNI152_T1_1mm_brain.nii.gz](website/atlases/MNI152_T1_1mm_brain.nii.gz))
        * See [run_warp_tck_to_mni.sh](databaseprep/run_warp_tck_to_mni.sh) and [nemo_convert_mni_tck_to_sparsemat.py](databaseprep/nemo_convert_mni_tck_to_sparsemat.py)
    3. Additional processing to facillitate efficient computation: [run_full_database_prep.sh](databaseprep/run_full_database_prep.sh)
2. Lesion to disconnectivity mapping: [nemo_lesion_to_chaco.py](nemo_lesion_to_chaco.py)
    1. Given a lesion mask, identify all streamlines it intersects, and identify the endpoints of those streamlines to compute brain regions for which we expect a reduction of connectivity
    2. Compute ChaCo (Change in Connectivity) score, which is the ratio of (disrupted streamlines)/(total streamlines) for each voxel or ROI (chacovol), or voxel/ROI pair (chacoconn). **0=no disconnection. 1=complete disconnection**

Additionally, we have created a user-friendly web interface to run this tool in the cloud (AWS):
* Main web GUI code in [uploader.js](website/uploader.js)
* Uploading via this website triggers an AWS Lambda event, which executes [s3-lambda.py](website/config/s3-lambda.py) to launch an AWS EC2 instance
* On the EC2 instance, [nemo_startup.sh](website/config/nemo_startup.sh) manages the entire input/output workflow, and uploads the results to S3, triggering a second AWS Lambda event in [s3-lambda.py](website/config/s3-lambda.py) that emails the user a link to the results

## Input
* **NOTE: All input volumes must already be transformed into 1mm MNI152 v6 space** (eg: using FSL's FNIRT or ANTs) 
    * 182x218x182 voxels (best) or 181x217x181 (this sometimes results if upsampling SPM 2mm output to 1mm)
* Lesion mask = NIfTI volume (*.nii.gz or *.nii)
* Parcellation (optional) = NIfTI volume with labeled voxels (*.nii.gz or *.nii)
* Resolution = mm resolution for outputs. Default=1mm, but this leads to large output files for the pairwise <code>chacoconn</code> and 420-subject <code>*\_allref.pkl</code>
    * e.g., For a single very extensive lesion mask, <code>chacovol\_allref</code> can be as large as 700MB, and <code>chacoconn\_allref</code> can be 10s of GB
* Currently, this package treats the lesion volume as a binary mask (0 = healthy tissue, >0 = tissue damage)
    
## Output
* <code>chacovol</code> = voxelwise or regionwise ChaCo ratio
* <code>chacoconn</code> = pairwise ChaCo ratio of loss of connections between pairs of voxels and/or ROIs
    * Note: for parcellations, these will be upper triangular. For voxelwise (including downsampled), this is not guaranteed
* <code>\_chacovol\_(mean|stdev)</code> = mean and stdev of all 420 HCP-subject ChaCo ratio maps (for voxelwise outputs, these are .nii.gz files)
* <code>\_chacoconn\_(mean|stdev)</code> = mean and stdev of all 420 HCP-subject pairwise disconnectivity maps
* <code>chacovol_allref.pkl</code> = ChaCo ratio map for each of the 420 HCP reference subjects
    * 420x(voxels or ROIs) sparse matrix format
* <code>chacoconn_allref.pkl</code> = ChaCo ratio map for each of the 420 HCP reference subjects
    * 420-element list of (voxels x voxels) or (ROIs x ROIs) sparse matrices
* <code>*\_allref\_denom.pkl</code> = denominator of the ChaCo ratio for each subject (useful when recomputing ChaCo numerator and denominator for reparcellating ratios)

* <code>*.pkl</code> are [Python pickle format](https://docs.python.org/3/library/pickle.html) that can be read using:
    <code>import pickle; data = pickle.load(open("filename.pkl","rb"))</code>
* <code>*.npz</code> are [SciPy sparse matrices](https://docs.scipy.org/doc/scipy/reference/sparse.html) that can be read using:
        <code>import numpy as np; from scipy import sparse; data = sparse.load\_npz("filename.npz")</code>
    
## Website usage
* Coming soon

## Details of tractography database
* Anatomical and diffusion data preprocessed by HCP using [Minimal Processing Pipeline](https://github.com/Washington-University/HCPpipelines) ([Glasser 2013](https://doi.org/10.1016/j.neuroimage.2013.04.127))
    * 3T diffusion MRI collected at 1.25mm resolution, 3 shells (b=1000,2000,3000), 90 directions per shell (See: [HCP 3T Protocol](https://protocols.humanconnectome.org/HCP/3T/imaging-protocols.html))
    * Gradient nonlinearity correction, EPI distortion correction, eddy current correction, motion correction, rigid-body registration to subject anatomy
* [MRtrix3](https://www.mrtrix.org/) was used to estimate a voxelwise multi-shell, multi-tissue constrained spherical deconvolution (CSD) model and then compute whole brain tractography for each HCP subject
    * [<code>5ttgen</code>](https://mrtrix.readthedocs.io/en/dev/reference/commands/5ttgen.html), [<code>dwi2response dhollander</code>](https://mrtrix.readthedocs.io/en/latest/reference/commands/dwi2response.html#dwi2response-dhollander), [<code>dwi2fod msmt\_csd</code>](https://mrtrix.readthedocs.io/en/latest/reference/commands/dwi2fod.html)
    * Probabilistic tractography with anatomical constraint (iFOD2+ACT) and dynamic seeding:
        * [<code>tckgen RF_wm_dhollander.mif tracts_ifod2act_5M.tck -algorithm iFOD2 -act 5TT.nii.gz -seed_dynamic RF_wm_dhollander.mif -cutoff 0.06 -maxlength 300 -select 5M</code>](https://mrtrix.readthedocs.io/en/latest/reference/commands/tckgen.html)
    * 5 million streamlines per subject
    * Additionally estimate SIFT2 weights for each streamline to better match global tractography to observed diffusion images ([<code>tcksift2</code>](https://mrtrix.readthedocs.io/en/latest/reference/commands/tcksift2.html))
* 3D streamline coordinates were then transformed into discretized 1mm MNI space
    * Uses the warp file from HCP <code>$SUBJID/MNINonLinear/xfms/standard2acpc\_dc.nii.gz</code> (Note this is the MNI->T1 volume warp that is used to map streamlines from T1->MNI)
    * Round (x,y,z) coordinates to the nearest integer, and for each subject create a (7M voxels)x(5M streamlines) binary sparse matrix describing which of the 7M voxels (182\*218\*182=7,221,032) each of the 5M streamlines passes through
* This set of 420 7Mx5M sparse matrices can be used to compute ChaCo scores, but would require downloading the entire 700GB database every single time we run the tool. Instead, we divide the sparsemats into 10x10x10 voxel "chunks", where each chunk file contains the [420*1000 x 5M] sparse matrix of streamlines for all 420 subjects through that cube of MNI space. Thus, we only download the "chunks" that overlap the input mask to determine which streamlines intersect our lesion. 

## Parcellations
* FreeSurfer86: 86-region FreeSurfer Desikan-Killiany (DKT) cortical atlas with "aseg" subcortical regions(ie: aparc+aseg.nii.gz) [Desikan 2006](https://pubmed.ncbi.nlm.nih.gov/16530430/), [Fischl 2002](https://pubmed.ncbi.nlm.nih.gov/11832223/)
    * This atlas includes the 70 cortical DKT regions + 16 subcortical (excluding brain-stem)
    * For this atlas, each of the 420 HCP reference subjects has their own subject-specific parcellation that we use when assigning streamlines to ROIs
* FreeSurferSUIT111: 111-region atlas with 70 DKT cortical + 14 aseg subcortical + 27 cerebellar subregions from the SUIT atlas [Diedrichsen 2009](https://pubmed.ncbi.nlm.nih.gov/19457380/)
    * Like the FreeSurfer86, this is a subject-specific parcellation
* FreeSurferAverage86: Same regions as FreeSurfer86 but defined as a single group-level MNI volume 
    * Each subject parcellation was mode-dilated by 1mm, then we computed the mode across all subjects
* AAL: 116-region Automated Anatomical Labeling atlas from [Tzourio-Mazoyer 2002](https://pubmed.ncbi.nlm.nih.gov/11771995/)
* CC200: 200-region whole-brain cortical+subcortical parcellation from [Craddock 2012](https://pubmed.ncbi.nlm.nih.gov/21769991/)
* CC400: 400-region (actually 392) cortical+subcortical parcellation from [Craddock 2012](https://pubmed.ncbi.nlm.nih.gov/21769991/)
* Shen268: 268-region cortical+subcortical atlas from [Shen 2013](https://pubmed.ncbi.nlm.nih.gov/23747961/)
* Yeo 2011 7-networks: 7-network CORTICAL-ONLY parcellation from [Yeo 2011](https://pubmed.ncbi.nlm.nih.gov/21653723/)
* Yeo 2011 17-networks: 17-network CORTICAL-ONLY parcellation from [Yeo 2011](https://pubmed.ncbi.nlm.nih.gov/21653723/)
* Custom: Any 1mm MNI (182x218x182) parcellation volume
* See files in [website/atlases/](website/atlases/)