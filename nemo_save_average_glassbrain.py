import nibabel as nib
from nilearn import plotting, image
import sys

outfile=sys.argv[1]
colormap=None
if sys.argv[2].startswith("--"):
    colormap=sys.argv[2][2:]
    imglist=sys.argv[3:]
else:
    imglist=sys.argv[2:]

avgdata=None
imgshape=None
for i in imglist:
    img=nib.load(i)
    imgdata=img.get_fdata()
    if avgdata is None:
        avgdata=imgdata
        imgshape=imgdata.shape
    else:
        if imgshape != imgdata.shape:
            sys.exit(1)
        avgdata+=imgdata

avgdata/=len(imglist)

imgavg=nib.Nifti1Image(avgdata,affine=img.affine, header=img.header)
plotting.plot_glass_brain(imgavg,output_file=outfile,cmap=colormap,colorbar=True)

print("%sx%sx%s" % imgshape)
