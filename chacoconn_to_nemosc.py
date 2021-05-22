import numpy as np
import pickle
from scipy.io import savemat
import sys
import argparse
import nibabel as nib

#example:
#python chacoconn_to_nemosc.py --chacoconn mylesion_nemo_output_chacoconn_fs86subj_allref.pkl \
# --denom mylesion_nemo_output_chacoconn_fs86subj_allref_denom.pkl \
# --roivol roivol_fs86_unrelated420_dwi.txt \
# --volnorm
# --output mylesion_nemo_output_chacoconn_fs86subj_nemoSC_volnorm.txt

def argument_parse_nemosc(argv):
    parser=argparse.ArgumentParser()
    parser.add_argument("--chacoconn",action="store",dest="chacofile")
    parser.add_argument("--denom",action="store",dest="denomfile")
    parser.add_argument("--roivol",action="store",dest="roivolfile")
    parser.add_argument("--output",action="store",dest="outfile")
    parser.add_argument("--outputstdev",action="store",dest="outfilestdev")
    parser.add_argument("--triu",action="store_true",dest="triu")
    parser.add_argument("--nodiag",action="store_true",dest="nodiag")
    parser.add_argument("--onlydenom",action="store_true",dest="onlydenom")
    
    args=parser.parse_args(argv)
    return args

def chacoconn_to_nemosc(chacofile,denomfile,outfile,outfile_stdev=None,roivolfile=None,do_triu=False,do_nodiag=False,do_onlydenom=False):
    C=pickle.load(open(chacofile,"rb"))
    D=pickle.load(open(denomfile,"rb"))
    roivolmat=None
    
    if roivolfile:
        if roivolfile.lower().endswith(".nii") or roivolfile.lower().endswith(".nii.gz"):
            parcimg=nib.load(roivolfile)
            parcvol=parcimg.get_fdata()
            _,roivol=np.unique(parcvol[parcvol>0],return_counts=True)
        elif roivolfile.lower().endswith(".txt"):
            roivol=np.loadtxt(roivolfile)
            if roivol.shape[1]!=C[0].shape[0]:
                roivol=roivol[:,-C[0].shape[0]:]
        if len(roivol.shape)==1:
            roivolmat=(np.atleast_2d(roivol)+np.atleast_2d(roivol).T)/2
        else:
            roivolmat=np.stack([(np.atleast_2d(roivol[i,:])+np.atleast_2d(roivol[i,:]).T)/2 for i in range(roivol.shape[0])], axis=2)
        
    
    #convert the list of RxR matrices into an R x R x RefSubj 3D matrix
    Cnew=np.stack([x.toarray() for x in C],axis=2)
    Dnew=np.stack([x.toarray() for x in D],axis=2)
    
    #compute estimated SC for each reference subject from (1-chaco)*reference
    #(element-wise multiplication)
    if not do_onlydenom:
        SC=(1-Cnew)*Dnew
    else:
        #in onlydenom case, we are computing the average SC for this atlas, ignoring the chaco info completely
        SC=Dnew
    
    #if roivols were provided (RefSubj x R), create a new R x R x RefSubj 3D matrix 
    # where Vmat[i,j,Subj]=(roivol[Subj,i]+roivol[Subj,j])/2
    # and then element-wise divide the estimated SC by this new volume normalization matrix
    if roivolmat is not None and len(roivolmat.shape)==3:
        SC=SC/roivolmat
    
    #compute the mean estimated SC (RxR) across all ref subjects
    SCmean=np.mean(SC,axis=2)
    SCstd=np.zeros(SCmean.shape)
    if outfile_stdev is not None:
        SCstd=np.std(SC,axis=2)
    
    if roivolmat is not None and len(roivolmat.shape)==2:
        SCmean=SCmean/roivolmat
        SCstd=SCstd/roivolmat
    
    if do_nodiag:
        SCmean[np.eye(SCmean.shape[0])>0]=0
        SCstd[np.eye(SCstd.shape[0])>0]=0
    
    if do_triu and do_nodiag:
        SCmean=np.atleast_2d(SCmean[np.triu(np.ones(SCmean.shape),k=1)>0])
        SCstd=np.atleast_2d(SCstd[np.triu(np.ones(SCstd.shape),k=1)>0])
    elif do_triu:
        SCmean=np.atleast_2d(SCmean[np.triu(np.ones(SCmean.shape),k=0)>0])
        SCstd=np.atleast_2d(SCstd[np.triu(np.ones(SCstd.shape),k=0)>0])
    
    if outfile.endswith(".mat"):
        savemat(outfile,{"SC":SCmean})	
    else:
        np.savetxt(outfile,SCmean,"%f")
    
    if outfile_stdev is not None:
        if outfile_stdev.endswith(".mat"):
            savemat(outfile_stdev,{"SC":SCstd})	
        else:
            np.savetxt(outfile_stdev,SCstd,"%f")

if __name__ == "__main__": 
    args=argument_parse_nemosc(sys.argv[1:])
    chacoconn_to_nemosc(chacofile=args.chacofile, denomfile=args.denomfile, outfile=args.outfile, outfile_stdev=args.outfilestdev,
        roivolfile=args.roivolfile, do_triu=args.triu, do_nodiag=args.nodiag,do_onlydenom=args.onlydenom)
