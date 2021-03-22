import numpy as np
import pickle
from scipy.io import savemat
import sys
import argparse

#example:
#python chacoconn_to_nemosc.py --chacoconn mylesion_nemo_output_chacoconn_fs86subj_allref.pkl \
# --denom mylesion_nemo_output_chacoconn_fs86subj_allref_denom.pkl \
# --roivol roivol_fs86_unrelated420_dwi.txt \
# --volnorm
# --output mylesion_nemo_output_chacoconn_fs86subj_nemoSC_volnorm.txt

parser=argparse.ArgumentParser()
parser.add_argument("--chacoconn",action="store",dest="chacofile")
parser.add_argument("--denom",action="store",dest="denomfile")
parser.add_argument("--roivol",action="store",dest="roivolfile")
parser.add_argument("--output",action="store",dest="outfile")
parser.add_argument("--triu",action="store_true",dest="triu")
parser.add_argument("--nodiag",action="store_true",dest="nodiag")

args=parser.parse_args()

chacofile=args.chacofile
denomfile=args.denomfile
outfile=args.outfile
do_triu=args.triu
do_nodiag=args.nodiag

C=pickle.load(open(chacofile,"rb"))
D=pickle.load(open(denomfile,"rb"))
roivol=None

if args.roivolfile:
	roivol=np.loadtxt(args.roivolfile)
	if roivol.shape[1]!=C[0].shape[0]:
		roivol=roivol[:,-C[0].shape[0]:]

#convert the list of RxR matrices into an R x R x RefSubj 3D matrix
Cnew=np.stack([x.toarray() for x in C],axis=2)
Dnew=np.stack([x.toarray() for x in D],axis=2)

#compute estimated SC for each reference subject from (1-chaco)*reference
#(element-wise multiplication)
SC=(1-Cnew)*Dnew

#if roivols were provided (RefSubj x R), create a new R x R x RefSubj 3D matrix 
# where Vmat[i,j,Subj]=(roivol[Subj,i]+roivol[Subj,j])/2
# and then element-wise divide the estimated SC by this new volume normalization matrix
if roivol is not None:
	roivolmat=np.stack([(np.atleast_2d(roivol[i,:])+np.atleast_2d(roivol[i,:]).T)/2 for i in range(roivol.shape[0])], axis=2)
	SC=SC/roivolmat

#compute the mean estimated SC (RxR) across all ref subjects
SCmean=np.mean(SC,axis=2)
if do_nodiag:
	SCmean[np.eye(SCmean.shape[0])>0]=0

if do_triu and do_nodiag:
	SCmean=np.atleast_2d(SCmean[np.triu(np.ones(SCmean.shape),k=1)>0])
elif do_triu:
	SCmean=np.atleast_2d(SCmean[np.triu(np.ones(SCmean.shape),k=0)>0])

if outfile.endswith(".mat"):
	savemat(outfile,{"SCmean":SCmean})	
else:
	np.savetxt(outfile,SCmean,"%f")

