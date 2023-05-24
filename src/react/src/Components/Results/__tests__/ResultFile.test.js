import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import {graphql, QueryRenderer} from 'react-relay';
import {MockPayloadGenerator} from 'relay-test-utils';
import ResultFile from '../ResultFile';
import userEvent from '@testing-library/user-event';

/* global environment */

describe('result file component', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment} query={graphql`
            query ResultFileTestQuery @relay_test_operation {
                bilbyResultFiles(jobId: 1) {
                    files {
                        ...ResultFile_file
                    }
                }
            }
          `}
            variables={{
                jobId: 'QmlsYnlKb2JOb2RlOjY='
            }}
            render={({error, props}) => {
                if (props) {
                    return <table>
                        <tbody>
                            <ResultFile
                                data={{bilbyJob: { id: 1 }}}
                                file={props.bilbyResultFiles.files[0]}
                                bilbyResultFiles={{jobType: 0}}
                            />
                        </tbody>
                    </table>;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockFile = {
        BilbyResultFile() {
            return {
                path: '/cool-path/',
                isDir: false,
                fileSize: 10,
                downloadToken: 'abc-token'
            };
        }
    };


    it('should render', () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('should render with data', async () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        await waitFor(() => environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockFile)
        ));
        expect(screen.getByText('/cool-path/')).toBeInTheDocument();
        expect(screen.getByText('File')).toBeInTheDocument();
        expect(screen.getByText('10 B')).toBeInTheDocument();
    });

    it('should have a clickable link that downloads a file', async () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        await waitFor(() => environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockFile)
        ));
        userEvent.click(screen.getByText('/cool-path/'));
        await waitFor(() => environment.mock.resolveMostRecentOperation(
            operation => MockPayloadGenerator.generate(operation)
        ));
        expect(screen.getByText('/cool-path/')).toBeInTheDocument();
        expect(screen.getByText('/cool-path/')).toHaveClass('link-visited');
    });

    it('should alert the user if there are errors in the download', async () => {
        expect.hasAssertions();
        const errorAlert = jest.spyOn(window, 'alert').mockImplementation(jest.fn());
        render(<TestRenderer />);
        await waitFor(() => environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockFile)
        ));
        userEvent.click(screen.getByText('/cool-path/'));
        await waitFor(() => environment.mock.resolveMostRecentOperation(
            () => (
                {
                    errors: [{ message: 'download failed' }],
                    data: {
                        generateFileDownloadIds: {
                            result: {}
                        }
                    }
                }
            )
        ));
        expect(errorAlert).toHaveBeenCalledWith('Unable to download file.');
    });
});
