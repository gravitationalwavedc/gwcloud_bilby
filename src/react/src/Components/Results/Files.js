import React, { useState } from 'react';
import {createFragmentContainer, graphql} from 'react-relay';
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
        {props.files ? (
            <Table>
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
                    {props.files.files.map((e, i) => 
                        <ResultFile
                            key={i} 
                            File={e} {...props}/>
                    )}
                </tbody>
            </Table>
        ) : (
            <h4>Job does not have any files</h4>
        )}
    </React.Fragment>;
};

export default createFragmentContainer(Files, {
    files: graphql`
        fragment Files_files on BilbyResultFiles {
            files {
                ...ResultFile_file
            }
        }
    `
});
