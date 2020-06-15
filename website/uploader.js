var uploadBucketName = "kuceyeski-wcm-web-upload";
var bucketRegion = "us-east-1";
var IdentityPoolId = "us-east-1:3d5d591e-9224-4321-a4dc-be72b2558b36";
var uploadFolder = "inputs";

var uploadTimer = null;
var passwordTimerInterval = 1000;
var uploadTimerInterval = 10000;
var uploadStatusSuffix = "_status.png";
var uploadTimerCount = 0;
var nemo_version_info = null;

var reslist=[];
var parclist=[];

var atlasinfo = {'aal': {'name': 'AAL', 'thumbnail':'images/thumbnail_aal.png','roicount':116},
    'cc200': {'name': 'CC200', 'thumbnail':'images/thumbnail_cc200.png','roicount':200},
    'cc400': {'name': 'CC400', 'thumbnail':'images/thumbnail_cc400.png','roicount':400},
    'shen268': {'name': 'Shen268', 'thumbnail':'images/thumbnail_shen268.png','roicount':268},
    'fs86avg': {'name': 'FreeSurferAverage86 (DKT+aseg)', 'thumbnail':'images/thumbnail_fs86.png','roicount':86},
    'fs86subj': {'name': 'FreeSurfer86 (subj-specific DKT+aseg)', 'thumbnail':'images/thumbnail_fs86.png','roicount':86},
    'fs111subj': {'name': 'FreeSurferSUIT111 (subj-specific DKT+aseg+SUIT cereb)', 'thumbnail':'images/thumbnail_fs111cereb.png','roicount':111},
    'yeo7': {'name': 'Yeo2011 7-networks', 'thumbnail':'images/thumbnail_yeo7.png', 'roicount':7},
    'yeo17': {'name': 'Yeo2011 17-networks', 'thumbnail':'images/thumbnail_yeo17.png', 'roicount':17},
};

AWS.config.update({
    region: bucketRegion,
    credentials: new AWS.CognitoIdentityCredentials({
        IdentityPoolId: IdentityPoolId
    })
});

var s3 = new AWS.S3({
    apiVersion: "2006-03-01",
    params: { Bucket: uploadBucketName }
});

function uuidv4() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c == 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
}

function timestamp(date) {
    if (date === undefined) date = new Date();
    var datestr = date.getUTCFullYear().toString() + ("0"+(date.getUTCMonth()+1)).substr(-2) + ("0"+date.getUTCDate()).substr(-2);
    var timestr = ("0"+date.getUTCHours()).substr(-2) + ("0"+date.getUTCMinutes()).substr(-2) + ("00"+date.getUTCSeconds()).substr(-2) + ("00"+date.getUTCMilliseconds()).substr(-3);
    return datestr+"_"+timestr;
}

function filesizestring(numbytes) {
    if(numbytes < 1024) {
        return numbytes.toString() + " B";
    } else if (numbytes < 1024*1024) {
        return Math.floor(numbytes/1024).toString() + " KB";
    } else {
        return Math.floor(numbytes/(1024*1024)).toString() + " MB";
    }
}

function dict2jsonkeyval(mydict){
    retlist=[];
    for(var k in mydict)
        retlist=retlist.concat({Key:k, Value:mydict[k]});
    return retlist;
}

function jsonkeyval2dict(jsonlist){
    retval={};
    for(i=0;i<jsonlist.length; i++)
        retval[jsonlist[i].Key]=jsonlist[i].Value;
    return retval;
}


function base64_encode(data){
    var str = data.reduce(function(a,b){ return a+String.fromCharCode(b) },'');
    return btoa(str).replace(/.{76}(?=.)/g,'$&\n');
}

function checkBucketStatus(bucket, key, statusdiv, password_success_message) {
    if(uploadTimer==null)
        return;
    uploadTimerCount++;
    //console.log("Count: " +  uploadTimerCount.toString());
    var s3params = {Bucket: bucket, Key: key+uploadStatusSuffix};
    s3.headObject(s3params, function(err, data) {
        if(err){
            //console.log("No object yet");
            return;
        }
        //console.log("Image is here!");
        //console.log(data);
        
        s3.getObjectTagging(s3params, function(err, tagdata) {
            if (err){
                //console.log("No tags yet");
                return;
            }
            //console.log("Tag is here!");
            tags=jsonkeyval2dict(tagdata.TagSet);
            //console.log("Count: " +  uploadTimerCount.toString());
            //console.log(tags);

            var statusimgdiv = document.getElementById("uploadstatusimage");
            
            if (tags["input_checks"]=="success"){
                s3.getObject(s3params,function(err,file){
                    statusimgdiv.innerHTML="</br><h4>Input lesion mask</h4></br><img src='data:image/png;base64," + base64_encode(file.Body)+"'>";
                });
            } else if(tags["input_checks"]=="error"){
                errorMessage("Input file error!");
            } else if(tags["password_status"]=="error"){
                errorMessage("Incorrect password!");
            } else if(tags["password_status"]=="success"){
                successMessage(password_success_message);
                if(uploadTimer != null)
                    clearInterval(uploadTimer);
                uploadTimerCount=0;
                uploadTimer = setInterval(function() {checkBucketStatus(bucket, key, statusdiv, password_success_message);}, uploadTimerInterval);
                return;
            }
            if(uploadTimer != null)
                clearInterval(uploadTimer);
            uploadTimer=null;
            uploadTimerCount=0;
        });
    });
}

function showUploader(run_internal_script) {
    if (run_internal_script === undefined) run_internal_script = false;
    extra_html='';
    if(run_internal_script){
        extra_html+=['<label for="outputlocation">Copy to S3 location: s3://</label>',
        '<input id="outputlocation" type="text" size="50" value="kuceyeski-wcm-temp/kwj2001/nemo_output"><br/><br/>',
        '<label for="coco_password">Password</label>',
        '<input id="coco_password" type="password" value=""><br/><br/>'].join('\n');
    }
    
    if(document.URL.startsWith("file:///"))
        extra_html+=['<input type="checkbox" id="debug" name="debug" value="1">',
        '<label for="debug">Run in debug mode</label><br/><br/>'].join('\n');
    
    var htmlTemplate = [
        '<div>',
        'Lesion mask must be in 1mm MNI152 space (same as FSL MNI152_T1_1mm.nii.gz or SPM avg152.nii)<br/>',
        'Voxel dimension should be 182x218x182 (or 181x217x181 for SPM)<br/>',
        '</div>',
        '<br/>',
        '<label for="email">E-mail address:</label>',
        '<input id="email" type="text" placeholder="email@address.com" size="30"><br/><br/>',
        '<label for="fileupload">MNI Lesion Nifti file:</label>',
        '<div class="filediv">',
        '<input id="fileupload" type="file" accept=".gz,.nii,.zip" class="fileinfo">',
        '<label id="filesize" class="fileinfo"></label>',
        '</div><br/><br/>',
        '<input type="checkbox" id="cumulative" name="cumulative" value="1">',
        '<label for="cumulative">Accumulate total hits along streamline</label><br/>',
        '<input type="checkbox" id="siftweights" name="siftweights" value="1" checked>',
        '<label for="siftweights">Weight streamlines by data fit (SIFT2)</label><br/>',
        '<input type="checkbox" id="smoothing" name="smoothing" value="1" checked>',
        '<label for="smoothing">Include smoothed mean images</label><br/><br/>',
        '<label for="addres_select">Add output resolution:</label>',
        getResolutionSelectHtml("addres_select"),
        '<button id="addres_button" class="button" onclick="addOutput(\'res\',\'addres_select\',false)">Add</button>',
        '<br/>',
        '<label for="addparc_select">Add output parcellation:</label>',
        getParcSelectHtml("addparc_select"),
        '<button id="addparc_button" class="button" onclick="addOutput(\'parc\',\'addparc_select\',false)">Add</button>',
        '<br/>',
        '<div id="resdiv"></div><div id="parcdiv"></div>',
        '<br/><br/>',
        extra_html,
        '<button id="upload" onclick="submitMask()" class="button">Submit File</button>',
        '<div id="uploadstatus"></div><div id="uploadstatusimage"></div>',
        '<div id="version" class="versiondiv"></div>'
    ];
    document.getElementById("app").innerHTML = htmlTemplate.join("\n");
    document.getElementById('fileupload').onchange = function(){
        var filesize = document.getElementById('fileupload').files[0].size;
        document.getElementById('filesize').innerHTML="(" + filesizestring(filesize) + ")";
    }
    addOutput("res",null,true);
    
    //get version info
    if(document.URL.startsWith("file:///")){
        document.getElementById('version').innerHTML="NeMo vLOCAL";
    } else {
        jsonurl='config/nemo-version.json';
        let request = new XMLHttpRequest();

        request.open('GET', jsonurl);
        request.responseType = 'json'; // now we're getting a string!
        request.send();

        request.onload = function() {
            nemo_version_info=request.response;
            document.getElementById('version').innerHTML="NeMo v"+nemo_version_info['nemo_version']+" - "+nemo_version_info['nemo_version_date'];
        }
    }
}

function updateStatusMessage(message,message_class, keep_buttons_disabled){
    let statusdiv = document.getElementById("uploadstatus");
    let statusimgdiv = document.getElementById("uploadstatusimage");
    
    statusdiv.className=message_class;
    statusdiv.innerHTML=message;
    
    if(!keep_buttons_disabled)
        document.getElementById("upload").disabled=false;
}

function successMessage(message, keep_buttons_disabled){
    updateStatusMessage(message,"statustext_good",keep_buttons_disabled);
}
function errorMessage(message,keep_buttons_disabled){
    updateStatusMessage(message,"statustext_bad",keep_buttons_disabled);
}

function neutralMessage(message,keep_buttons_disabled){
    updateStatusMessage(message,"statustext_neutral",keep_buttons_disabled);
}



function getResolutionSelectHtml(id){
    htmlTemplate=['<select id="'+id+'" name="'+id+'">'];
    htmlTemplate.push('<option value="none">[SELECT]</option>');
    for(var i=1; i<=10; i++){
        htmlTemplate.push('<option value="'+i+'">'+i+' mm</option>');
    }
    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function getParcSelectHtml(id){
    htmlTemplate=['<select id="'+id+'" name="'+id+'">'];
    htmlTemplate.push('<option value="none">[SELECT]</option>');
    atlasnames=Object.keys(atlasinfo);
    for(var i = 0; i < atlasnames.length; i++){
        htmlTemplate.push('<option value="'+atlasnames[i]+'">'+atlasinfo[atlasnames[i]]['name']+'</option>');
    }

    htmlTemplate.push('<option value="custom">[Upload atlas]</option>');
    htmlTemplate.push('</select>');
    return htmlTemplate.join("\n");
}

function addOutput(parc_or_res, select_id, init1mm){
    var allrefchecked=""
    var pairwisechecked=""
    if(init1mm){
        var selvalue="1";
        var seltext="1 mm";
    } else {
        var myselect = document.getElementById(select_id);
        var selvalue=myselect.options[myselect.options.selectedIndex].value;
        if(selvalue=="none"){
            return;
        }
        var seltext=myselect.options[myselect.options.selectedIndex].text;
        allrefchecked="checked"
        pairwisechecked="checked"
    }
    
    if (parc_or_res=="parc" && selvalue != "custom" ){
        if(parclist.indexOf(selvalue)>=0)
            return;
        parclist.push(selvalue);
    } else if (parc_or_res=="res"){
        if(reslist.indexOf(selvalue)>=0)
            return;
        reslist.push(selvalue);
    }
    var parentdiv = document.getElementById(parc_or_res+"div");
    
    var newid=getNextAvailableId("add"+parc_or_res,1);
    var newindex=newid.replace("add"+parc_or_res,"");
    
    var newdiv = document.createElement("div");
    newdiv.className="parcdiv";
    newdiv.id=newid; 
    
    var newfileinput_id=null;
    var newfilelabel_id=null;
    
    htmlTemplate=[];
    htmlTemplate.push('<button onclick="removeOutput(\''+newid+'\')" style="float:right">X</button>');
    if (parc_or_res == "parc") {
        if (selvalue=="custom") {
            newfileinput_id=newid+'_fileupload';
            newfilelabel_id=newid+'_filesize';
            newparctext="parc"+("000000"+newindex).substr(-3);
            htmlTemplate.push('Custom parcellation name: ',
            '<input id="'+newid+'_customname" type="text" size="25" value="'+newparctext+'">',
            '<br/><br/>',
            '<input id="'+newfileinput_id+'" type="file" accept=".gz,.nii" class="fileinfo">',
            '<label id="'+newfilelabel_id+'" class="fileinfo"></label>');
        } else {
            if(atlasinfo[selvalue] && atlasinfo[selvalue]['thumbnail'])
                htmlTemplate.push('<div style="float:right; padding-right: 20pt"><img src="'+atlasinfo[selvalue]['thumbnail']+'"></div>');
            
            htmlTemplate.push('Parcellation name: '+seltext,
            '<input id="'+newid+'_name" type="hidden" value="'+selvalue+'">');
        }
    } else if (parc_or_res=="res") {
        htmlTemplate.push('Resolution: '+seltext,
        '<input id="'+newid+'_name" type="hidden" value="'+selvalue+'">');
    }
    
    htmlTemplate.push('<br/><br/><input type="checkbox" id="'+newid+'_pairwise" name="'+newid+'_pairwise" value="1" '+pairwisechecked+'>',
        '<label for="'+newid+'_pairwise">Compute pairwise disconnectivity</label><br/>',
        '<input type="checkbox" id="'+newid+'_output_allref" name="'+newid+'_output_allref" value="1" '+allrefchecked+'>',
        '<label for="'+newid+'_output_allref">Output ChaCo for each reference subject (large file size)</label><br/>');
    
    //    '<input type="checkbox" id="'+newid+'_output_denom" name="'+newid+'_output_denom" value="1" checked>',
    //    '<label for="'+newid+'_output_denom">Output denominator for each reference subject (large file size. Useful for re-parcellation)</label>');
    
    
    newdiv.innerHTML=htmlTemplate.join("\n");
    parentdiv.appendChild(newdiv);
    
    if (newfileinput_id != null) {
        document.getElementById(newfileinput_id).onchange = function(){
            var filesize = document.getElementById(newfileinput_id).files[0].size;
            document.getElementById(newfilelabel_id).innerHTML="(" + filesizestring(filesize) + ")";
        }
    }
}

function removeOutput(id){
    var outputname=document.getElementById(id+"_name")
    if (outputname != null) {
        if (id.startsWith("addparc")){
            var idx=parclist.indexOf(outputname.value);
            if(idx>=0)
                parclist.splice(idx,1);
        } else if(id.startsWith("addres")) {
            var idx=reslist.indexOf(outputname.value);
            if(idx>=0)
                reslist.splice(idx,1);
        }
    }
    document.getElementById(id).remove();
    
}

function getNextAvailableId(idprefix,startindex){
    var i=startindex;
    while(document.getElementById(idprefix+i)!=null)
        i++;
    return idprefix+i;
}

function submitMask() {
    if(uploadTimer != null){
        clearInterval(uploadTimer); 
        uploadTimer=null;
    }

    var files = document.getElementById("fileupload").files;
    var email = document.getElementById("email").value;
    var cumulative = document.getElementById("cumulative").checked;
    var smoothing = document.getElementById("smoothing").checked;
    var siftweights = document.getElementById("siftweights").checked;
    var statusdiv = document.getElementById("uploadstatus");
    var statusimgdiv = document.getElementById("uploadstatusimage");
    var outputlocation = document.getElementById("outputlocation");
    var cocopassword = document.getElementById("coco_password");
    var debug_input = document.getElementById("debug");
    
    neutralMessage("...",true);
    document.getElementById("upload").disabled=true;
    statusimgdiv.innerHTML="";
    
    var uploadFolderKey = encodeURIComponent(uploadFolder) + "/";
    var newTimestamp=timestamp() 
    
    var outputs_taglist=[];
    var outputs_prefixlist=[];
    
    var resdivchildren = document.getElementById("resdiv").childNodes;
    var parcdivchildren = document.getElementById("parcdiv").childNodes;
    var resparc=Array.prototype.slice.call(resdivchildren).concat(Array.prototype.slice.call(parcdivchildren));
    for(var i=0; i<resparc.length; i++){
        var this_id=resparc[i].id;
        var this_pairwise=document.getElementById(this_id+"_pairwise").checked;
        var this_output_allref=document.getElementById(this_id+"_output_allref").checked;
        var this_customname=document.getElementById(this_id+"_customname");
        var this_name=document.getElementById(this_id+"_name");
        var this_filenode=document.getElementById(this_id+"_fileupload");
        
        if(this_customname != null)
            this_name=this_customname.value;
        else
            this_name=this_name.value;
        
        var this_newkey=""
        if (this_filenode != null){
            if(!this_filenode.files.length){
                errorMessage("Please choose a parcellation file to upload first!")
                return;
            }
            var this_file=this_filenode.files[0];
            var this_filename=this_file.name;
            var this_lowername=this_filename.toLowerCase();
            var this_fileext="";
            if(this_lowername.endsWith(".nii.gz"))
                this_fileext=".nii.gz";
            else if(this_lowername.endsWith(".nii"))
                this_fileext=".nii";
            else {
                errorMessage("Unknown file extension for "+this_filename+". Must be .nii.gz, .nii");
                return;
            }
            

            var newKey=uploadFolderKey + newTimestamp + "/" + this_name + this_fileext;
            this_newkey=newKey;
            
            var upload = new AWS.S3.ManagedUpload({
            params: {
                Bucket: uploadBucketName,
                Key: newKey,
                Body: this_file,
                ACL: "bucket-owner-full-control" 
            }});

            var promise = upload.promise();

            promise.then(
            function(data) {
                console.log("Successfully uploaded atlas file: "+this_filename)
            },
            function(err) {
                errorMessage("There was an error uploading your atlas file: "+err.message)
                console.log(err);
                return;
            });
        }
        //remove the "add"
        //var this_prefix=this_id.substr(3);
        var this_prefix=this_id;
        
        if (this_id.startsWith("addres")) {
            //res=1, pairwise, allref, 
            //addres1_pairwise=True, addres1_allref=True, addres1_res=1
            outputs_taglist=outputs_taglist.concat([{Key: this_prefix+"_res", Value: this_name}, {Key: this_prefix+"_pairwise", Value: this_pairwise}, {Key: this_prefix+"_allref", Value: this_output_allref}]);

        } else if(this_id.startsWith("addparc")) {
            //addparc1_pairwise=True, addparc1_allref=True, addparc1_name=cc200, addparc1_file=parc001.nii.gz
            outputs_taglist=outputs_taglist.concat([{Key: this_prefix+"_name", Value: this_name}, {Key: this_prefix+"_pairwise", Value: this_pairwise}, {Key: this_prefix+"_allref", Value: this_output_allref}]);
            
            if(this_newkey.length>0)
                outputs_taglist.push({Key: this_prefix+"_filekey", Value: this_newkey});
        }
        outputs_prefixlist.push(this_prefix);
        //console.log(this_id, this_pairwise, this_output_allref, this_name);
    }
    if(outputs_prefixlist.length>0)
        outputs_taglist.push({Key: "output_prefix_list", Value: outputs_prefixlist.join(",")});
    //console.log(outputs_taglist);

    if (!files.length) {
        errorMessage("Please choose a file to upload first!");
        return;
    }
    if (!email.length) {
        errorMessage("Please enter an email!")
        return;
    }
    var file = files[0];
    var fileName = file.name;

    var lowername=fileName.toLowerCase();

    var fileext=""
    if (lowername.endsWith(".nii.gz")) {
        fileext=".nii.gz"
    } else if (lowername.endsWith(".nii")) {
        fileext=".nii"
    } else if (lowername.endsWith(".zip")) {
        fileext=".zip"
    } else if (lowername.endsWith(".tar.gz")) {
        fileext=".tar.gz"
    } else if (lowername.endsWith(".tar")) {
        fileext=".tar"
    } else {
        errorMessage("Unknown file extension for "+fileName+". Must be .nii.gz, .nii, .zip, .tar, .tar.gz")
        return;
    }
    
    var newFileName=newTimestamp + "/" + uuidv4() + fileext;
    var newKey=uploadFolderKey + newFileName;

    //var photoKey = albumPhotosKey + fileName;

    // Use S3 ManagedUpload class as it supports multipart uploads

    // Object can only have 10 tags! Only take 
    taglist=[{Key: 'filename', Value: fileName}, {Key: 'email', Value: email},
        {Key: 'timestamp', Value: newTimestamp}, {Key: 'unixtime', Value: Date.now()}, 
        {Key: 'status_suffix', Value: uploadStatusSuffix}];

    if (outputlocation) taglist.push({Key: 'outputlocation', Value: outputlocation.value});
    if (cocopassword) taglist.push({Key: 'coco_password', Value: cocopassword.value});
    if (debug_input) taglist.push({Key: 'debug', Value: debug_input.checked});
    
    var config_taglist=[{Key: 'smoothing', Value: smoothing}, {Key: 'siftweights', Value: siftweights}, {Key: 'cumulative', Value: cumulative}];
    config_taglist=taglist.concat(dict2jsonkeyval(nemo_version_info));
    config_taglist=config_taglist.concat(config_taglist);
    
    if (outputs_taglist.length)
        config_taglist=config_taglist.concat(outputs_taglist);
    //////////////////////////////////////////////////////////
    var jsonse=JSON.stringify(config_taglist);
    var blob = new Blob([jsonse], {type: "application/json"});
    
    var upload = new AWS.S3.ManagedUpload({
    params: {
        Bucket: uploadBucketName,
        Key: newKey+"_config.json",
        Body: blob,
        ACL: "bucket-owner-full-control" 
    }
    });

    //console.log(upload)
    var promise = upload.promise();

    promise.then(
    function(data) {
        console.log("Successfully uploaded config");
    },
    function(err) {
        errorMessage("There was an error uploading your config: "+err.message);
        console.log(err);
        return;
    });
    
    //return;
    //////////////////////////////////////////////////////////
    
    //original: ACL: 'public-read'
    var upload = new AWS.S3.ManagedUpload({
    params: {
        Bucket: uploadBucketName,
        Key: newKey,
        Body: file,
        ACL: "bucket-owner-full-control" 
    },
    tags: taglist
    });

    //console.log(upload)
    var promise = upload.promise();

    promise.then(
    function(data) {
        if(cocopassword){
            neutralMessage("Validating password...", true);
            timer_interval=passwordTimerInterval;
        } else {
            successMessage("Uploaded successfully!<br/>Results with be emailed to "+email+" when complete (check spam box!)")
            timer_interval=uploadTimerInterval;
        }
        if(uploadTimer == null){
            uploadTimerCount=0;
            password_success_message="Uploaded successfully!<br/>Results with be emailed to "+email+" when complete (check spam box!)";
            uploadTimer = setInterval(function() {checkBucketStatus(uploadBucketName, newKey, statusdiv, password_success_message);}, timer_interval);
        } 
    },
    function(err) {
        errorMessage("There was an error uploading your lesion mask: "+err.message);
        console.log(err);
        return;
    });
}
