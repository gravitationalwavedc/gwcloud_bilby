import { commitMutation, createFragmentContainer, graphql } from 'react-relay';
import { filesize } from 'filesize';
import { jobTypes } from '../../Utils/jobHelpers';
import environment from '../../environment';

const downloadUrl = 'https://jobcontroller.adacs.org.au/job/apiv1/file/?fileId=';
const uploadedJobDownloadUrl = import.meta.env.DEV
    ? 'http://localhost:8001/file_download/?fileId='
    : 'https://gwcloud.org.au/file_download/?fileId=';

const getFileDownloadIdMutation = graphql`
    mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
        generateFileDownloadIds(input: $input) {
            result
        }
    }
`;

const generateDownload = (url) => {
    // Generate a file download link and click it to download the file
    const link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
};

const performFileDownload = (e, jobId, jobTypeId, token, filePath) => {
    e.preventDefault();
    e.target.classList.add('link-visited');

    if (jobTypeId === jobTypes.EXTERNAL) {
        // For external jobs, the filePath is the full URL to the remote end. Just generate the URL and send the user
        // there
        generateDownload(filePath);
        return;
    }

    if (jobTypeId === jobTypes.UPLOADED) {
        // For uploaded jobs, we can optionally skip the need to generate a download id
        generateDownload(uploadedJobDownloadUrl + token);
        return;
    }

    commitMutation(environment, {
        mutation: getFileDownloadIdMutation,
        variables: {
            input: {
                jobId: jobId,
                downloadTokens: [token],
            },
        },
        onCompleted: (response, errors) => {
            if (errors) {
                alert('Unable to download file.');
            } else {
                generateDownload(downloadUrl + response.generateFileDownloadIds.result[0]);
            }
        },
    });
};

const ResultFile = ({ file, data, bilbyResultFiles }) => (
    <tr>
        <td>
            {file.isDir ? (
                file.path
            ) : (
                <a
                    href="#"
                    onClick={(e) =>
                        performFileDownload(
                            e,
                            data.bilbyJob.id,
                            bilbyResultFiles.jobType,
                            file.downloadToken,
                            file.path,
                        )
                    }
                >
                    {file.path}
                </a>
            )}
        </td>
        <td>{file.isDir ? 'Directory' : 'File'}</td>
        <td>{file.isDir || file.fileSize === null ? '' : filesize(parseInt(file.fileSize), { round: 0 })}</td>
    </tr>
);

export default createFragmentContainer(ResultFile, {
    file: graphql`
        fragment ResultFile_file on BilbyResultFile {
            path
            isDir
            fileSize
            downloadToken
        }
    `,
});
