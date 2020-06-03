// Set the harnessApi
import {createMockEnvironment, MockPayloadGenerator} from "relay-test-utils";
import {QueryRenderer} from 'react-relay';
import {setHarnessApi} from "../../index";
import JobResultFile from "./JobResultFile";
import React from "react";
import {graphql} from "react-relay";
import {expect} from "@jest/globals";
import TestRenderer from 'react-test-renderer';

setHarnessApi({
    getEnvironment: name => {
        return createMockEnvironment();
    }
})

test('Test File Result', () => {
    const environment = createMockEnvironment();
    const MyTestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query JobResultFileTestFileQuery @relay_test_operation {
                  bilbyResultFiles: bilbyResultFiles(jobId: 1) {
                    files {
                      ...JobResultFile_bilbyResultFile
                    }
                  }
                }
              `}
            variables={{}}
            render={({error, props}) => {
                if (props) {
                    return <JobResultFile bilbyResultFile={props.bilbyResultFiles.files[0]} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const renderer = TestRenderer.create(<MyTestRenderer />);
    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            ID(_, generateId) {
                // Why we're doing this?
                // To make sure that we will generate a different set of ID
                // for elements on first page and the second page.
                return `result-file-is-file-${generateId()}`;
            },
            BilbyResultFile() {
                return {
                    isDir: false,
                    path: "/this/is/a.file",
                    fileSize: 1024*102,
                    downloadId: "ba82f910-c4f3-464c-8465-b53a2f51b853"
                }
            }
        }),
    );

    expect(renderer).toMatchSnapshot();
});

test('Test Directory Result', () => {
    const environment = createMockEnvironment();
    const MyTestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query JobResultFileTestDirectoryQuery @relay_test_operation {
                  bilbyResultFiles: bilbyResultFiles(jobId: 1) {
                    files {
                      ...JobResultFile_bilbyResultFile
                    }
                  }
                }
              `}
            variables={{}}
            render={({error, props}) => {
                if (props) {
                    return <JobResultFile bilbyResultFile={props.bilbyResultFiles.files[0]} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const renderer = TestRenderer.create(<MyTestRenderer />);
    environment.mock.resolveMostRecentOperation(operation =>
        MockPayloadGenerator.generate(operation, {
            ID(_, generateId) {
                // Why we're doing this?
                // To make sure that we will generate a different set of ID
                // for elements on first page and the second page.
                return `result-file-is-directory-${generateId()}`;
            },
            BilbyResultFile() {
                return {
                    isDir: true,
                    path: "/this/is/a.directory",
                    fileSize: 1024*506,
                    downloadId: "2a47fab3-3a09-44b6-a0d5-0fc37b792258"
                }
            }
        }),
    );

    expect(renderer).toMatchSnapshot();
});