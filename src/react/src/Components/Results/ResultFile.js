import React from 'react';
import {commitMutation, createFragmentContainer, graphql} from 'react-relay';
import filesize from 'filesize';
import {harnessApi} from '../../index';
import {IS_DEV} from '../../Utils/misc';

const downloadUrl = 'https://gwcloud.org.au/job/apiv1/file/?fileId=';
const uploadedJobDownloadUrl =
    IS_DEV ? 'http://localhost:8001/file_download/?fileId=' : 'https://gwcloud.org.au/bilby/file_download/?fileId=';

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

const performFileDownload = (e, jobId, jobType, token) => {
    e.preventDefault();
    e.target.classList.add('link-visited');

    if (jobType === 1) {
        // For uploaded jobs, we can optionally skip the need to generate a download id
        generateDownload(uploadedJobDownloadUrl + token);
        return;
    }

    commitMutation(harnessApi.getEnvironment('bilby'), {
        mutation: getFileDownloadIdMutation,
        variables: {
            input: {
                jobId: jobId,
                downloadTokens: [token]
            }
        },
        onCompleted: (response, errors) => {
            if (errors) {
                // eslint-disable-next-line no-alert
                alert('Unable to download file.');
            }
            else {
                generateDownload(downloadUrl + response.generateFileDownloadIds.result[0]);
            }
        },
    });
};

const ResultFile = ({file, data, bilbyResultFiles}) =>
    <tr>
        <td>
            {
                file.isDir ? file.path : (
                    <a
                        href='#'
                        onClick={
                            e => performFileDownload(
                                e,
                                data.bilbyJob.id,
                                bilbyResultFiles.jobType,
                                file.downloadToken
                            )
                        }
                    >
                        {file.path}
                    </a>
                )
            }
        </td>
        <td>{file.isDir ? 'Directory' : 'File'}</td>
        <td>{file.isDir ? '' : filesize(parseInt(file.fileSize), {round: 0})}</td>
    </tr>;

export default createFragmentContainer(ResultFile, {
    file: graphql`
        fragment ResultFile_file on BilbyResultFile {
            path
            isDir
            fileSize
            downloadToken
        }
    `
});
