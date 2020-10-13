import React from 'react';
import {Route} from 'found';
import MyJobs from './Pages/MyJobs';
import PublicJobs from './Pages/PublicJobs';
import {graphql} from 'react-relay';
import {harnessApi} from './index';
import NewJob from './Pages/NewJob';
import DuplicateJobForm from './Components/Forms/DuplicateJobForm';
import ViewJob from './Pages/ViewJob';
import Loading from './Components/Loading';
import {RedirectException} from 'found';

const handleRender = ({Component, props}) => {
    if (!Component || !props)
        return <Loading/>;

    if (!harnessApi.hasAuthToken())
        throw new RedirectException('/auth/?next=' + props.match.location.pathname, 401);
  
    return <Component data={props} {...props}/>;
};

function getRoutes() {
    return (
        <Route>
            <Route
                Component={PublicJobs}
                query={graphql`
                query Routes_HomePage_Query (
                  $count: Int!,
                  $cursor: String,
                  $search: String,
                  $timeRange: String,
                ) {
                    gwclouduser {
                      username
                    }
                    ...PublicJobs_data
                }
              `}
                prepareVariables={() => ({
                    timeRange: 'all',
                    count: 100
                })}
                environment={harnessApi.getEnvironment('bilby')}
                render={handleRender}/>
            <Route
                path="job-form"
                Component={NewJob}
                render={handleRender}/>
            <Route
                path="job-form/duplicate/"
                query={graphql`
                    query Routes_JobForm_Query ($jobId: ID!){
                      ...DuplicateJobForm_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(params, {location}) => ({
                    jobId: location.state && location.state.jobId ? location.state.jobId : ''
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={DuplicateJobForm}
                render={handleRender}/>
            <Route
                path="job-list"
                query={graphql`
                    query Routes_JobList_Query(
                      $count: Int!,
                      $cursor: String,
                      $orderBy: String
                    ) {
                      ...MyJobs_data
                    }
                `}
                prepareVariables={() => ({
                    count: 100,
                    timeRange: 'all',
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={MyJobs}
                render={handleRender}/>
            <Route
                path="job-results/:jobId/"
                environment={harnessApi.getEnvironment('bilby')}
                Component={ViewJob}
                query={graphql`
                    query Routes_ViewJob_Query ($jobId: ID!){
                      ...ViewJob_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(params) => ({
                    jobId: params.jobId
                })}
                render={handleRender}
            />
        </Route>
    );
}

export default getRoutes;
