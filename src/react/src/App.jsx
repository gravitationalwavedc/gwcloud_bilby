import React from 'react';
import MyJobs from './Pages/MyJobs';
import PublicJobs from './Pages/PublicJobs';
import { graphql, RelayEnvironmentProvider } from 'react-relay';
import NewJob from './Pages/NewJob';
import DuplicateJobForm from './Components/Forms/DuplicateJobForm';
import Layout from './Layout'
import ViewJob from './Pages/ViewJob';
import { INFINITE_SCROLL_CHUNK_SIZE } from './constants';
import { handlePrivateRender, handlePublicRender } from './routeHandlers';
import './assets/scss/theme.scss';
import './assets/styles.scss';
import environment from './environment';
import { BrowserProtocol, queryMiddleware } from 'farce';
import {
  createFarceRouter,
  createRender,
  makeRouteConfig,
  Route,
} from 'found';
import { Resolver } from 'found-relay';

function App() {

  const Router = createFarceRouter({

    historyProtocol: new BrowserProtocol(),
    historyMiddlewares: [queryMiddleware],
    routeConfig: makeRouteConfig(
      <>
        <Route path="/" Component={Layout}>
          <Route
            Component={PublicJobs}
            query={graphql`
                    query App_HomePage_Query($count: Int!, $cursor: String, $search: String, $timeRange: String) {
                        ...PublicJobs_data
                    }
                `}
            prepareVariables={() => ({
              timeRange: 'all',
              count: INFINITE_SCROLL_CHUNK_SIZE,
            })}
            // environment={environment}
            render={handlePublicRender}
          />
          <Route
            path="job-form"
            Component={NewJob}
            render={handlePrivateRender}
            query={graphql`
                    query App_NewJob_Query {
                        ...DataForm_data
                    }
                `}
          // environment={environment}
          />
          <Route
            path="job-form/duplicate/"
            query={graphql`
                    query App_JobForm_Query($jobId: ID!) {
                        ...DuplicateJobForm_data @arguments(jobId: $jobId)
                    }
                `}
            prepareVariables={(_, { location }) => ({
              jobId: location.state && location.state.jobId ? location.state.jobId : '',
            })}
            environment={environment}
            Component={DuplicateJobForm}
            render={handlePrivateRender}
          />
          <Route
            path="job-list"
            query={graphql`
                    query App_JobList_Query($count: Int!, $cursor: String, $orderBy: String) {
                        ...MyJobs_data
                    }
                `}
            prepareVariables={() => ({
              count: INFINITE_SCROLL_CHUNK_SIZE,
              timeRange: 'all',
            })}
            // environment={environment}
            Component={MyJobs}
            render={handlePrivateRender}
          />
          <Route
            path="job-results/:jobId/"
            // environment={environment}
            Component={ViewJob}
            query={graphql`
                    query App_ViewJob_Query($jobId: ID!) {
                        ...ViewJob_data @arguments(jobId: $jobId)
                    }
                `}
            prepareVariables={(params) => ({
              jobId: params.jobId,
            })}
            render={handlePrivateRender}
          />
        </Route>
      </>
    ),
    render: createRender({})
  });


  return <Router resolver={new Resolver(environment)} />
}

export default App
