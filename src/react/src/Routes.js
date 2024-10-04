import React from 'react';
import { Route } from 'found';
import MyJobs from './Pages/MyJobs';
import PublicJobs from './Pages/PublicJobs';
import { graphql } from 'react-relay';
import { harnessApi } from './index';
import NewJob from './Pages/NewJob';
import DuplicateJobForm from './Components/Forms/DuplicateJobForm';
import ViewJob from './Pages/ViewJob';
import { INFINITE_SCROLL_CHUNK_SIZE } from './constants';
import { handlePrivateRender, handlePublicRender } from './routeHandlers';

function getRoutes() {
    return (
        <Route>
            <Route
                Component={PublicJobs}
                query={graphql`
                    query Routes_HomePage_Query($count: Int!, $cursor: String, $search: String, $timeRange: String) {
                        ...PublicJobs_data
                    }
                `}
                prepareVariables={() => ({
                    timeRange: 'all',
                    count: INFINITE_SCROLL_CHUNK_SIZE,
                })}
                environment={harnessApi.getEnvironment('bilby')}
                render={handlePublicRender}
            />
            <Route
                path="job-form"
                Component={NewJob}
                render={handlePrivateRender}
                query={graphql`
                    query Routes_NewJob_Query {
                        ...DataForm_data
                    }
                `}
                environment={harnessApi.getEnvironment('bilby')}
            />
            <Route
                path="job-form/duplicate/"
                query={graphql`
                    query Routes_JobForm_Query($jobId: ID!) {
                        ...DuplicateJobForm_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(_, { location }) => ({
                    jobId: location.state && location.state.jobId ? location.state.jobId : '',
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={DuplicateJobForm}
                render={handlePrivateRender}
            />
            <Route
                path="job-list"
                query={graphql`
                    query Routes_JobList_Query($count: Int!, $cursor: String, $orderBy: String) {
                        ...MyJobs_data
                    }
                `}
                prepareVariables={() => ({
                    count: INFINITE_SCROLL_CHUNK_SIZE,
                    timeRange: 'all',
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={MyJobs}
                render={handlePrivateRender}
            />
            <Route
                path="job-results/:jobId/"
                environment={harnessApi.getEnvironment('bilby')}
                Component={ViewJob}
                query={graphql`
                    query Routes_ViewJob_Query($jobId: ID!) {
                        ...ViewJob_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(params) => ({
                    jobId: params.jobId,
                })}
                render={handlePrivateRender}
            />
        </Route>
    );
}

export default getRoutes;
