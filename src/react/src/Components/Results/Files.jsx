import { QueryRenderer, graphql } from 'react-relay';
import Table from 'react-bootstrap/Table';
import ResultFile from './ResultFile';
import environment from '../../environment';

const Files = (props) => (
    <>
        <Table style={props.hidden ? { display: 'none' } : {}}>
            <thead>
                <tr>
                    <th>File Path</th>
                    <th>Type</th>
                    <th>File Size</th>
                </tr>
            </thead>
            <tbody>
                <QueryRenderer
                    environment={environment}
                    query={graphql`
                        query FilesQuery($jobId: ID!) {
                            bilbyResultFiles(jobId: $jobId) {
                                files {
                                    ...ResultFile_file
                                }
                                jobType
                            }
                        }
                    `}
                    variables={{ jobId: props.data.bilbyJob.id }}
                    render={(_result) => {
                        const _error = _result.error;
                        const _props = _result.props;

                        if (_error) {
                            return (
                                <tr>
                                    <td colSpan={3}>
                                        <div>{_error.message}</div>
                                    </td>
                                </tr>
                            );
                        } else if (_props && _props.bilbyResultFiles) {
                            return (
                                <>
                                    {_props.bilbyResultFiles.files.map((file) => (
                                        <ResultFile key={file.path} file={file} {..._props} {...props} />
                                    ))}
                                </>
                            );
                        }

                        return (
                            <tr>
                                <td colSpan={3}>Loading...</td>
                            </tr>
                        );
                    }}
                />
            </tbody>
        </Table>
    </>
);

export default Files;
