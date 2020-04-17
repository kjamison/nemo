function Asp = mrtrix_tracks_to_sparse(trackfile,xform_vox2xyz,volsize)

%use version that doesn't do the cell conversion
A=read_mrtrix_tracks_fast(trackfile);

Txyz2vox=inv(xform_vox2xyz);

sub2ind_fast=@(sz,x,y,z)1+(x-1)+sz(1)*(y-1)+sz(1)*sz(2)*(z-1);
xyz2voxidx=@(x)sub2ind_fast(volsize,...
    max(1,min(volsize(1),round(Txyz2vox(1,1)*x(:,1)+Txyz2vox(1,4)+1))),...
    max(1,min(volsize(2),round(Txyz2vox(2,2)*x(:,2)+Txyz2vox(2,4)+1))),...
    max(1,min(volsize(3),round(Txyz2vox(3,3)*x(:,3)+Txyz2vox(3,4)+1))));

%dnan=isnan(A.data(:,1));
%dnanidx=find(dnan);

Avoxidx=xyz2voxidx(A.data);
%xyz2voxidx output doesn't have nans so put them back in
%may not be necessary if we get isnan from the xcoord first
Avoxidx(isnan(A.data(:,1)))=nan;

Avoxidx=Avoxidx([Avoxidx(1:end-1)~=Avoxidx(2:end); true]);

dnan=isnan(Avoxidx);
dnanidx=find(dnan);

trackstart=[1; dnanidx(1:end-1)+1];
trackstop=dnanidx-1;
tracklen=trackstop-trackstart+1;

trackidx=zeros(size(Avoxidx));
trackidx(trackstart)=1;
trackidx=cumsum(trackidx);
%vals=np.ones(np.sum(~dnan))
%indptr=cumsum([1; tracklen]);
%A=csc_matrix((vals,(data[~dnan],trackidx[~dnan])),shape=(np.prod(volsize),len(trackstart)))
%A=csc_matrix((vals,data[~dnan],indptr),shape=(np.prod(volsize),len(trackstart)))
Asp=sparse(Avoxidx(~dnan),trackidx(~dnan),1,prod(volsize),numel(trackstart))>0;
