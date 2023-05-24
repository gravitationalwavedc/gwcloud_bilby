import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import {MockPayloadGenerator} from 'relay-test-utils';
import Files from '../Files';
import {jobTypes} from '../../../Utils/jobHelpers';

/* global environment */


describe('files', () => {
    const mockEnvironment = environment;

    jest.mock('../../../index', () => ({
        harnessApi: {
            getEnvironment: () => mockEnvironment
        }
    }));

    const mockFile = {
        BilbyResultFiles() {
            return {
                jobType: jobTypes.NORMAL,
                files: [
                    {
                        path: '/b-cool-path/',
                        isDir: false,
                        fileSize: 10,
                    },
                    {
                        path: '/a-cooler-path/',
                        isDir: false,
                        fileSize: 15,
                    }

                ]
            };
        }
    };

    it('should render', () => {
        expect.hasAssertions();
        render(<Files data={{bilbyJob: {id: 1}}} />);
        expect(screen.getByText('Loading...')).toBeInTheDocument();
    });

    it('should render with data', async () => {
        expect.hasAssertions();
        render(<Files data={{bilbyJob: {id: 1}}} />);
        await waitFor(() => environment.mock.resolveMostRecentOperation(
            operation => MockPayloadGenerator.generate(
                operation, mockFile
            )));
        expect(screen.getByText('/b-cool-path/')).toBeInTheDocument();
        expect(screen.getByText('/a-cooler-path/')).toBeInTheDocument();
    });
});
