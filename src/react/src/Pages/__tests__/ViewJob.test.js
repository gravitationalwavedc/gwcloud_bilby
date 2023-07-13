import React from 'react';
import { graphql, QueryRenderer } from 'react-relay';
import { MockPayloadGenerator } from 'relay-test-utils';
import { render, waitFor, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import ViewJob from '../ViewJob';

/* global environment, router */

describe('view job page', () => {
    const TestRenderer = () => (
        <QueryRenderer
            environment={environment}
            query={graphql`
                query ViewJobTestQuery($jobId: ID!) @relay_test_operation {
                    ...ViewJob_data @arguments(jobId: $jobId)
                }
            `}
            variables={{
                jobId: 'QmlsYnlKb2JOb2RlOjY=',
            }}
            render={({ error, props }) => {
                if (props) {
                    return <ViewJob data={props} match={{ params: { jobId: 'QmlsYnlKb' } }} router={router} />;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockBilbyJobReturn = {
        EventIDType() {
            return {
                eventId: 'test-1',
                triggerId: 'trigger-1',
                nickname: 'slayer',
            };
        },
        BilbyJobNode() {
            return {
                id: 'QmlsYnlKb2JOb2RlOjY=',
                userId: 1,
                lastUpdated: '2020-10-05 04:47:02 UTC',
                private: false,
                jobStatus: {
                    name: 'Error',
                    number: '400',
                    date: '2020-10-05 04:49:58 UTC',
                },
                params: {
                    details: {
                        name: 'GW-Sim-test32',
                        description: 'A simulated binary black hole test job using 32s priors.',
                        private: true,
                    },
                    data: {
                        dataChoice: 'real',
                        triggerTime: '1253509434.066406',
                        channels: {
                            hanfordChannel: 'GDS-CALIB_STRAIN',
                            livingstonChannel: 'GDS-CALIB_STRAIN',
                            virgoChannel: null,
                        },
                    },
                    detector: {
                        hanford: true,
                        hanfordMinimumFrequency: '20',
                        hanfordMaximumFrequency: '1024',
                        livingston: true,
                        livingstonMinimumFrequency: '20',
                        livingstonMaximumFrequency: '1024',
                        virgo: false,
                        virgoMinimumFrequency: '20',
                        virgoMaximumFrequency: '1024',
                        duration: '8',
                        samplingFrequency: '16384',
                    },
                    prior: {
                        priorDefault: '4s',
                    },
                    sampler: {
                        nlive: '1000',
                        nact: null,
                        maxmcmc: null,
                        walks: '50',
                        dlogz: null,
                        cpus: 1,
                        samplerChoice: 'dynesty',
                    },
                    waveform: {
                        model: 'binaryBlackHole',
                    },
                },
                labels: [
                    {
                        LabelType() {
                            return {
                                name: 'Review Requested',
                                id: 'TGFiZWxUeXBlOjM=',
                            };
                        },
                    },
                ],
                eventId: null,
            };
        },
    };

    const mockBilbyJobResultsFiles = {
        BilbyResultFile() {
            return {
                path: 'a_cool_path',
                isDir: false,
                fileSize: 1234,
                downloadId: 'anDownloadId',
            };
        },
    };

    it('should render a loading page', () => {
        expect.hasAssertions();
        const { getByText } = render(<TestRenderer />);
        expect(getByText('Loading...')).toBeInTheDocument();
    });

    it('should render the actual page', async () => {
        expect.hasAssertions();
        const { getByText, getAllByText } = render(<TestRenderer />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockBilbyJobReturn),
            ),
        );
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockBilbyJobResultsFiles),
            ),
        );
        expect(getByText('GW-Sim-test32')).toBeInTheDocument();
        expect(getAllByText('a_cool_path')[0]).toBeInTheDocument();
    });

    it('should change event id when using the Event ID modal', async () => {
        expect.hasAssertions();
        render(<TestRenderer />);
        await waitFor(() =>
            environment.mock.resolveMostRecentOperation((operation) =>
                MockPayloadGenerator.generate(operation, mockBilbyJobReturn),
            ),
        );

        expect(screen.queryByText('Event ID: test-1')).not.toBeInTheDocument();

        const changeEventIdBtn = screen.getByText('Set Event ID');
        userEvent.click(changeEventIdBtn);
        const modalInput = screen.getByRole('combobox');
        userEvent.click(modalInput);
        const idSelection = screen.getByLabelText('test-1');
        userEvent.click(idSelection);
        expect(screen.queryByText('Event ID: test-1')).toBeInTheDocument();
        expect(screen.queryByText('Change Event ID')).toBeInTheDocument();
    });
});
