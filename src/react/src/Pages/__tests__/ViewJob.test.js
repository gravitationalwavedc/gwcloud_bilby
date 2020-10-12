import React from 'react';
import { QueryRenderer, graphql } from 'react-relay';
import { MockPayloadGenerator } from 'relay-test-utils';
import { render, waitFor } from '@testing-library/react';
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
                jobId: 'QmlsYnlKb2JOb2RlOjY='
            }}
            render={({ error, props }) => {
                if (props) {
                    return <ViewJob data={props} match={{params: {jobId: 'QmlsYnlKb'}}} router={router}/>;
                } else if (error) {
                    return error.message;
                }
                return 'Loading...';
            }}
        />
    );

    const mockBilbyJobReturn = {
        BilbyJobNode() {
            return {
                userId:1,
                lastUpdated:'2020-10-05 04:47:02 UTC',
                start:{
                    name:'GW-Sim-test32',
                    description:'A simulated binary black hole test job using 32s priors.',
                    private:true
                },
                jobStatus:{
                    name:'Error',
                    number:'400',
                    date:'2020-10-05 04:49:58 UTC'
                },
                data:{
                    dataChoice:'simulated',
                    hanford:true,
                    livingston:true,
                    virgo:true,
                    signalDuration:'24 seconds',
                    samplingFrequency:'2048 hz',
                    triggerTime:'1126259462.391',
                    hanfordMinimumFrequency:'20',
                    hanfordMaximumFrequency:'1024',
                    hanfordChannel:'GWOSC',
                    livingstonMinimumFrequency:'20',
                    livingstonMaximumFrequency:'1024',
                    livingstonChannel:'GWOSC',
                    virgoMinimumFrequency:'20',
                    virgoMaximumFrequency:'1024',
                    virgoChnnel:'GWOSC',
                    id:'RGF0YVR5cGU6Ng=='
                },
                signal:{
                    signalChoice:'binaryBlackHole',
                    signalModel:'none',
                    mass1:'30.0',
                    mass2:'25.0',
                    luminosityDistance:'2000.0',
                    psi:'0.4',
                    iota:'2.659',
                    phase:'1.3',
                    mergerTime:'1126259642.413',
                    ra:'1.375',
                    dec:'-1.2108',
                    id:'U2lnbmFsVHlwZTo2'
                },
                prior:{
                    priorChoice:'4s',
                    id:'UHJpb3JUeXBlOjY='
                },
                sampler:{
                    samplerChoice:'dynesty',
                    nlive:'1000.0',
                    nact:'10.0',
                    maxmcmc:'5000.0',
                    walks:'1000.0',
                    dlogz:'0.1',
                    cpus:'1.0',
                    id:'U2FtcGxlclR5cGU6Ng=='
                },
                id:'QmlsYnlKb2JOb2RlOjY=',
                labels: [{
                    LabelType() { 
                        return {
                            name:'Review Requested',
                            id:'TGFiZWxUeXBlOjM='
                        };
                    }
                }]
            };
        },
        BilbyResultFile() {
            return {
                path: 'a_cool_path',
                isDir: false,
                fileSize: 1234,
                downloadId: 'anDownloadId'
            };
        },
        BilbyJobResultsFiles() {
            return {
                id: '123123',
                files: [
                    {BilbyResultFile() {
                        return {
                            path: 'a_cool_path',
                            isDir: false,
                            fileSize: 1234,
                            downloadId: 'anDownloadId'
                        };
                    }}
                ]
            };
        }
    };

    it('should render a loading page', () => {
        expect.hasAssertions();
        const { getByText } = render(<TestRenderer />);
        expect(getByText('Loading...')).toBeInTheDocument();
    });

    it('should render the actual page', async () => {
        expect.hasAssertions();
        const { getByText, getAllByText } = render(<TestRenderer />);
        await waitFor(() => environment.mock.resolveMostRecentOperation(operation =>
            MockPayloadGenerator.generate(operation, mockBilbyJobReturn)
        ));   
        expect(getByText('GW-Sim-test32')).toBeInTheDocument();
        expect(getAllByText('a_cool_path')[0]).toBeInTheDocument();
    });

});
