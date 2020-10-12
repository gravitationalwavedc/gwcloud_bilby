import React, { useState } from 'react';
import {QueryRenderer, graphql} from 'react-relay';
import {harnessApi} from '../../index';
import Table from 'react-bootstrap/Table';
import ResultFile from './ResultFile';

const Files = (props) => {
    const [order, setOrder] = useState('last_updated');
    const [direction, setDirection ] = useState('ascending');

    const handleSort = (clickedColumn) => {
        // This is very inelegant
        if (order !== clickedColumn) {
            setOrder(clickedColumn);
            setDirection('ascending');        
        } else {
            setOrder(order);
            setDirection(direction === 'ascending' ? 'descending' : 'ascending');
        }
    };
    
    return <React.Fragment>
        <Table style={props.hidden ? { display: 'none'} : {}}>
            <thead>
                <tr>
                    <th 
                        sorted={order === 'path' ? direction : null}
                        onClick={() => handleSort('path')}>
                            File Path
                    </th>
                    <th 
                        sorted={order === 'isDir' ? direction : null}
                        onClick={() => handleSort('isDir')}>
                          Type
                    </th>
                    <th 
                        sorted={order === 'fileSize' ? direction : null}
                        onClick={() => handleSort('fileSize')}>
                          File Size
                    </th>
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
                            } 
                          }
                        `}
                    variables={{jobId: props.data.bilbyJob.id }}
                    render={({error, props}) => {
                        if(error) {
                            return <div>{error.message}</div>;
                        } else if (props) {
                            return <React.Fragment>
                                {props.bilbyResultFiles.files.map((e, i) => 
                                    <ResultFile
                                        key={i} 
                                        file={e} {...props}/>)}
                            </React.Fragment>;
                        }

                        return <tr><td colSpan={3}>Loading...</td></tr>;}} />
            </tbody>
        </Table>
    </React.Fragment>;
};

export default Files;
