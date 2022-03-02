import React, { useState } from 'react';
import {QueryRenderer, graphql} from 'react-relay';
import {harnessApi} from '../../index';
import Table from 'react-bootstrap/Table';
import ResultFile from './ResultFile';

const Files = (props) => <React.Fragment>
    <Table style={props.hidden ? { display: 'none'} : {}}>
        <thead>
            <tr>
                <th>File Path</th>
                <th>Type</th>
                <th>File Size</th>
            </tr>
        </thead>
        <tbody>
            <QueryRenderer
                environment={harnessApi.getEnvironment('bilby')}
                query={graphql`
                          query FilesQuery ($jobId: ID!) {
                            bilbyResultFiles(jobId: $jobId) {
                              files {
                                ...ResultFile_file
                              }
                              isUploadedJob
                            } 
                          }
                        `}
                variables={{jobId: props.data.bilbyJob.id }}
                render={(_result) => {
                    const _error = _result.error;
                    const _props = _result.props;

                    if(_error) {
                        return <tr><td colSpan={3}><div>{_error.message}</div></td></tr>;
                    } else if (_props && _props.bilbyResultFiles) {
                        return <React.Fragment>
                            {
                                _props.bilbyResultFiles.files.map(
                                    (e, i) =>
                                        <ResultFile
                                            key={i}
                                            file={e}
                                            {..._props}
                                            {...props}
                                        />
                                )
                            }
                        </React.Fragment>;
                    }

                    return <tr><td colSpan={3}>Loading...</td></tr>;}} />
        </tbody>
    </Table>
</React.Fragment>;

export default Files;
