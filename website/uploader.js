var uploadBucketName = "kuceyeski-wcm-web-upload";
var bucketRegion = "us-east-1";
var IdentityPoolId = "us-east-1:3d5d591e-9224-4321-a4dc-be72b2558b36";
var uploadFolder = "inputs";

var uploadTimer = null;
var passwordTimerInterval = 1000;
var uploadTimerInterval = 10000;
var uploadStatusSuffix = "_status.png";
var uploadTimerCount = 0;

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

function jsonToDict(jsonlist){
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
            tags=jsonToDict(tagdata.TagSet);
            //console.log("Count: " +  uploadTimerCount.toString());
            //console.log(tags);
            if (tags["input_checks"]=="success"){
                s3.getObject(s3params,function(err,file){
                    statusdiv.innerHTML+="</br><h4>Input lesion mask</h4></br><img src='data:image/png;base64," + base64_encode(file.Body)+"'>";
                });
            } else if(tags["input_checks"]=="error"){
                statusdiv.className="statustext_bad";
                statusdiv.innerHTML="<br/>Input file error!";
            } else if(tags["password_status"]=="error"){
                statusdiv.className="statustext_bad";
                statusdiv.innerHTML="<br/>Incorrect password!";
            } else if(tags["password_status"]=="success"){
                statusdiv.className="statustext_good";
                statusdiv.innerHTML=password_success_message;
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
        extra_html=['<label for="outputlocation">Copy to S3 location: s3://</label>',
        '<input id="outputlocation" type="text" size="50" value="kuceyeski-wcm-temp/kwj2001/nemo_output"><br/><br/>',
        '<label for="coco_password">Password</label>',
        '<input id="coco_password" type="password" value=""><br/><br/>'].join('\n');
    }
    var htmlTemplate = [
        '<div>',
        'Lesion mask must be in 1mm MNI152 space (same as FSL MNI152_T1_1mm.nii.gz or SPM avg152.nii)<br/>',
        'Voxel dimension should be 182x218x182 (or 181x217x181 for SPM)<br/>',
        '</div>',
        '<br/>',
        '<label for="email">E-mail address:</label>',
        '<input id="email" type="text" value="test@test" size="30"><br/><br/>',
        '<label for="fileupload">MNI Lesion Nifti file:</label>',
        '<div class="filediv">',
        '<input id="fileupload" type="file" accept=".gz,.nii,.zip" class="fileinfo">',
        '<label id="filesize" class="fileinfo"></label>',
        '</div><br/><br/>',
        '<input type="checkbox" id="siftweights" name="siftweights" value="1" checked>',
        '<label for="siftweights">Weight streamlines by data fit (SIFT2)</label><br/><br/>',
        '<input type="checkbox" id="smoothing" name="smoothing" value="1" checked>',
        '<label for="smoothing">Include smoothed mean images</label><br/><br/>',
        '<input type="checkbox" id="output_allref" name="output_allref" value="1" checked>',
        '<label for="output_allref">Output map for each reference subject (large file size)</label><br/><br/>',
        extra_html,
        '<button id="upload" onclick="uploadFile()" class="uploadbutton">',
        "Upload File",
        "</button>",
        '<div id="uploadstatus"></div>'
    ];
    document.getElementById("app").innerHTML = getHtml(htmlTemplate);
    document.getElementById('fileupload').onchange = function(){
        var filesize = document.getElementById('fileupload').files[0].size;
        document.getElementById('filesize').innerHTML="(" + filesizestring(filesize) + ")";
    }
    return;
}

function uploadFile() {
    if(uploadTimer != null){
    clearInterval(uploadTimer); 
    uploadTimer=null;
    }

    var files = document.getElementById("fileupload").files;
    var email = document.getElementById("email").value;
    var output_allref = document.getElementById("output_allref").checked;
    var smoothing = document.getElementById("smoothing").checked;
    var siftweights = document.getElementById("siftweights").checked;
    var statusdiv = document.getElementById("uploadstatus");
    var outputlocation = document.getElementById("outputlocation");
    var cocopassword = document.getElementById("coco_password");

    statusdiv.className="statustext_neutral"
    statusdiv.innerHTML="..."
    if (!files.length) {
        statusdiv.className="statustext_bad";
        statusdiv.innerHTML="<br/>Please choose a file to upload first!";
        return;
        //return alert("Please choose a file to upload first.");
    }
    if (!email.length) {
        statusdiv.className="statustext_bad";
        statusdiv.innerHTML="<br/>Please enter an email!";
        return;
        //return alert("Please enter an email.");
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
        return alert("Unknown file extension for. Must be .nii.gz, .nii, .zip, .tar, .tar.gz");
    }

    var uploadFolderKey = encodeURIComponent(uploadFolder) + "/";

    var newTimestamp=timestamp() 
    var newFileName=newTimestamp + "/" + uuidv4() + fileext;
    var newKey=uploadFolderKey + newFileName;

    //var photoKey = albumPhotosKey + fileName;

    // Use S3 ManagedUpload class as it supports multipart uploads

    taglist=[{Key: 'filename', Value: fileName}, {Key: 'email', Value: email}, {Key: 'output_allref', Value: output_allref}, 
        {Key: 'smoothing', Value: smoothing}, {Key: 'siftweights', Value: siftweights}, {Key: 'timestamp', Value: newTimestamp},
        {Key: 'unixtime', Value: Date.now()}, {Key: 'status_suffix', Value: uploadStatusSuffix}];

    if (outputlocation) taglist.push({Key: 'outputlocation', Value: outputlocation.value});
    if (cocopassword) taglist.push({Key: 'coco_password', Value: cocopassword.value});

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
            statusdiv.className="statustext_neutral";
            statusdiv.innerHTML="<br/>Validating password...";
            timer_interval=passwordTimerInterval;
        } else {
            statusdiv.className="statustext_good";
            statusdiv.innerHTML="<br/>Uploaded successfully!<br/>Results with be emailed to "+email+" when complete (check spam box!)";
            timer_interval=uploadTimerInterval;
        }
        //alert("Successfully uploaded lesion mask.");
        if(uploadTimer == null){
            uploadTimerCount=0;
            password_success_message="<br/>Uploaded successfully!<br/>Results with be emailed to "+email+" when complete (check spam box!)";
            uploadTimer = setInterval(function() {checkBucketStatus(uploadBucketName, newKey, statusdiv, password_success_message);}, timer_interval);
        } 
    },
    function(err) {
        statusdiv.className="statustext_bad";
        statusdiv.innerHTML="<br/>Failed!";
        console.log(err);
        return alert("There was an error uploading your lesion mask: ", err.message);
    });
}
