import React from 'react';
import {createFragmentContainer, graphql} from 'react-relay';
import filesize from 'filesize';

const downloadUrl = 'https://gwcloud.org.au/job/apiv1/file/?fileId=';

const ResultFile = ({file}) => 
    <tr>
        <td>
            {
                file.isDir ? file.path : (
                    <a 
                        href={downloadUrl + file.downloadId}
                        target="_blank" rel="noreferrer">
                        {file.path}
                    </a>
                )
            }
        </td>
        <td content={file.isDir ? 'Directory' : 'File'}/>
        <td content={filesize(file.fileSize, {round: 0})}/>
    </tr>;

export default createFragmentContainer(ResultFile, {
    file: graphql`
        fragment ResultFile_file on BilbyResultFile {
            path
            isDir
            fileSize
            downloadId
        }
    `
});
