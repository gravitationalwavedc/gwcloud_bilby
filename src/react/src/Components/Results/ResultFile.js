import React from 'react';
import {commitMutation, createFragmentContainer, graphql} from 'react-relay';
import filesize from 'filesize';
import {harnessApi} from '../../index';

const downloadUrl = 'https://gwcloud.org.au/job/apiv1/file/?fileId=';

const getFileDownloadIdMutation = graphql`
  mutation ResultFileMutation($input: GenerateFileDownloadIdsInput!) {
    generateFileDownloadIds(input: $input) {
      result
    }
  }
`;

const performFileDownload = (e, jobId, token) => {
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
                // Generate a file download link and click it to download the file
                const link = document.createElement('a');
                link.href = downloadUrl + response.generateFileDownloadIds.result[0];
                link.target = '_blank';
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            }
        },
    });

    e.preventDefault();
};

const ResultFile = ({file, data}) =>
    <tr>
        <td>
            {
                file.isDir ? file.path : (
                    <a 
                        href="#"
                        onClick={e => performFileDownload(e, data.bilbyJob.id, file.downloadToken)}
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
