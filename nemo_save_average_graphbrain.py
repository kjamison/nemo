import sys
import argparse 
import numpy as np
import pickle
from matplotlib import pyplot as plt
from scipy import sparse
import nibabel as nib
from nilearn import plotting
from nemo_save_average_matrix_figure import make_triangular_matrix_symmetric, average_input_matrices
from nemo_save_average_glassbrain import parcellation_to_volume, average_input_list

def argument_parse_savegraphbrain(argv):
    parser=argparse.ArgumentParser(description='Save a graphbrain image for an input chacoconn or average or multiple input chacoconns')
    
    parser.add_argument('--out','-o',action='store', dest='outfile', required=True,help='output image file (eg: chacoconn.png)')
    parser.add_argument('--cmap','--colormap','-c',action='store', dest='colormap',help='matplotlib colormap name (eg: jet,hot,...). Default: hot')
    parser.add_argument('--title','-t',action='store',dest='title',help='title to draw on top of figure')
    parser.add_argument('--maxsize',action='store',dest='maxsize',type=float,default=1000,help='Maximum matrix dimension to display. Default: 1000')
    parser.add_argument('--nodefile',action='store',dest='nodefile',help='File with ROI coordinates for graphbrain plotting. Either .nii.gz or .txt')
    parser.add_argument('--nodeview',action='store',dest='nodeview',default="lzr", help='Graphbrain view (eg: lzr, ortho). Default: lzr')
    parser.add_argument('--maxedgecount',action='store',dest='maxedges_count',type=float,default=1000, help='Maximum number of edges for graphbrain view. Default: 1000. Use smallest edge count from (count,percentile)')
    parser.add_argument('--maxedgepercentile',action='store',dest='maxedges_percentile',type=float,default=90, help='Edge strength percentile for graphbrain view. Default: 90. Use smallest edge count from (count,percentile)')
    parser.add_argument('--bgmaxscale',action='store',type=float,help='For graphbrain with parcellated glassbrain background colormap=[0 scale*(abs(max))]')
    parser.add_argument('--bgmaxpercentile',action='store',type=float,help='For graphbrain with parcellated glassbrain background, colormap=[0 percentile(scale)]')
    parser.add_argument('--bginput',nargs='*',action='store',dest='bginput')
    parser.add_argument('--bgcmap','--bgcolormap',action='store',dest='bgcolormap')
    parser.add_argument('--bgparcellation',action='store',dest='bgparcellation')
    parser.add_argument('connfile',nargs='*',action='store',help='one or more input connfiles (eg: chacoconn.pkl files)')
    
    args=parser.parse_args(argv)
    
    if not args.connfile:
        print("Must provide at least one input connfile!",file=sys.stderr)
        parser.print_help()
        exit(0)
    
    return args

def get_node_coords(nodefile):
    if nodefile.lower().endswith(".nii.gz") or nodefile.lower().endswith(".nii"):
        nodeimg=nib.load(nodefile)
        nodevol=nodeimg.get_fdata()
        j,i,k=np.meshgrid(np.arange(nodevol.shape[1]),np.arange(nodevol.shape[0]),np.arange(nodevol.shape[2]))
        ijk=np.reshape(np.stack([i,j,k]),(3,-1))
        
        #transform voxel ijk to mm xyz
        xyz=nodeimg.affine[:3,:3] @ ijk + nodeimg.affine[:3,3][:,None]
        
        nodemask=nodevol!=0
        nodevolmask=nodevol[nodemask]
        ulabels=np.unique(nodevolmask)
        xyzmask=xyz[:,nodemask.flatten()]
        nodexyz=np.vstack([np.mean(xyzmask[:,nodevolmask==u],axis=1) for u in ulabels])
    elif nodefile.lower().endswith("txt"):
        nodexyz=np.loadtxt(nodefile)
        if nodexyz.shape[1]>nodexyz.shape[0]:
            nodexyz=nodexyz.T
    else:
        print("Unknown nodefile format: %s" % (nodefile),file=sys.stderr)
        exit(1)
        
    return nodexyz

def save_graphbrain_fig(outputfile, inputlist, nodefile, colormap=None, title=None ,maxsize=None, nodeview=None, maxedges=1000, maxedgeperc=90,
        bginputlist=None, bgparcellation=None, bgcolormap=None, bgmaxscale=None, bgmaxpercentile=None):
    
    avgdata,imgshape = average_input_matrices(inputlist,sym=True,maxsize=maxsize)
    if imgshape is None:
        print("Mismatched input sizes", file=sys.stderr)
        return None
        
    if colormap is None:
        colormap="black_red_r"
    nodexyz=get_node_coords(nodefile)
    
    num_nodes=imgshape[0]
    
    if nodexyz.shape[0] != num_nodes:
        print("Matrix size %dx%d does not match node count %d in nodefile" % (imgshape[0],imgshape[1],nodexyz.shape[0]),file=sys.stderr)
        return None
        
    maxnodesize=50
    nodesize_range=[1,maxnodesize]
    
    edge_range=[0,np.max(avgdata)]
    #vecdata_norm=(vecdata-np.min(vecdata))/(np.max(vecdata)-np.min(vecdata))
    #nodesizes=vecdata_norm*(nodesize_range[1]-nodesize_range[0])+nodesize_range[0]
    
    nodesizes=10
    if num_nodes > 100:
        nodesizes=5
    
    num_edges=(num_nodes*num_nodes-num_nodes)/2
    edge_threshold=(100-100*maxedges/num_edges)
    if maxedgeperc is not None:
        edge_threshold=max(edge_threshold,maxedgeperc)
    edge_threshold_str="%.2f%%" % (edge_threshold)
    
    if bginputlist is None:
        #disp_fig=None
        #disp_outfile=outputfile
        plotting.plot_connectome(avgdata,nodexyz, edge_threshold=edge_threshold_str,edge_cmap=colormap,display_mode=nodeview,
            node_size=nodesizes,edge_vmin=edge_range[0],edge_vmax=edge_range[1],colorbar=True,title=title,output_file=outputfile)
    else:
        #in background case, load and plot the glassbrain background, then use the nilearn internal 
        #add_graph function to plot the lines
        bgavgdata, bgimgshape=average_input_list(bginputlist)
        if bgimgshape is None:
            print("Mismatched bginput sizes", file=sys.stderr)
            return None
        
        if bgparcellation is None:
            if len(bgimgshape)<3:
                print("Missing bgparcellation for this parcellated bginput.",file=file.stderr)
                return None
            refimg=nib.load(bginputlist[0])
        else:
            refimg=nib.load(bgparcellation)        
            parcvol=refimg.get_fdata()
            bgavgdata=parcellation_to_volume(bgavgdata,parcvol)
        
        bgvmax=None
        if bgmaxscale is not None:
            bgvmax=bgmaxscale*np.max(bgavgdata)
        elif bgmaxpercentile is not None:
            bgvmax=np.percentile(bgavgdata,bgmaxpercentile)
            
        bgimgavg=nib.Nifti1Image(bgavgdata,affine=refimg.affine, header=refimg.header)
        display=plotting.plot_glass_brain(bgimgavg,cmap=bgcolormap,title=title,vmax=bgvmax,colorbar=False)
        
        display.add_graph(avgdata, nodexyz,
                          node_size=nodesizes,
                          edge_cmap=colormap,
                          edge_vmin=edge_range[0], edge_vmax=edge_range[1],
                          edge_threshold=edge_threshold_str,
                          colorbar=True)
        display.savefig(outputfile)
        display.close()
                          
    #nodeview="lzr"
    #nodeview="ortho"
    #plotting.plot_connectome(avgdata,nodexyz, edge_threshold=edge_threshold_str,edge_cmap=colormap,display_mode=nodeview,
    #   node_size=nodesizes,edge_vmin=edge_range[0],edge_vmax=edge_range[1],colorbar=True,title=title,output_file=outputfile,figure=disp_fig)
    
    return imgshape

if __name__ == "__main__":
    args=argument_parse_savegraphbrain(sys.argv[1:])
    imgshape=save_graphbrain_fig(outputfile=args.outfile, inputlist=args.connfile, nodefile=args.nodefile, 
        colormap=args.colormap, title=args.title, maxsize=args.maxsize, nodeview=args.nodeview,
        maxedges=args.maxedges_count, maxedgeperc=args.maxedges_percentile,
        bginputlist=args.bginput, bgparcellation=args.bgparcellation,bgcolormap=args.bgcolormap, 
        bgmaxscale=args.bgmaxscale, bgmaxpercentile=args.bgmaxpercentile)
    
    if imgshape is None:
        #mismatched input sizes
        sys.exit(1)
    else:
    	#print("%sx%sx%s" % imgshape)
        print("x".join([str(x) for x in imgshape]))