import MyJobs from './Pages/MyJobs';
import PublicJobs from './Pages/PublicJobs';
import APIToken from './Pages/APIToken';
import { graphql } from 'react-relay';
import NewJob from './Pages/NewJob';
import DuplicateJobForm from './Components/Forms/DuplicateJobForm';
import Layout from './Layout';
import ViewJob from './Pages/ViewJob';
import { INFINITE_SCROLL_CHUNK_SIZE } from './constants';
import { handlePrivateRender, handlePublicRender } from './routeHandlers';
import './assets/scss/theme.scss';
import './assets/styles.scss';
import environment from './environment';
import { BrowserProtocol, queryMiddleware } from 'farce';
import { createFarceRouter, createRender, makeRouteConfig, Route } from 'found';
import { Resolver } from 'found-relay';

function App() {
    const Router = createFarceRouter({
        historyProtocol: new BrowserProtocol(),
        historyMiddlewares: [queryMiddleware],
        routeConfig: makeRouteConfig(
            <>
                <Route
                    path="/"
                    Component={Layout}
                    query={graphql`
                        query App_Layout_Query {
                            ...Layout_sessionUser
                        }
                    `}
                    render={handlePublicRender}
                >
                    <Route
                        Component={PublicJobs}
                        query={graphql`
                            query App_HomePage_Query(
                                $count: Int!
                                $cursor: String
                                $search: String
                                $timeRange: String
                            ) {
                                ...PublicJobs_data
                            }
                        `}
                        prepareVariables={() => ({
                            timeRange: 'all',
                            count: INFINITE_SCROLL_CHUNK_SIZE,
                        })}
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
                        Component={MyJobs}
                        render={handlePrivateRender}
                    />
                    <Route
                        path="job-results/:jobId/"
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
                    <Route
                        path="api-token"
                        Component={APIToken}
                        query={graphql`
                            query App_APIToken_Query {
                                ...APIToken_data
                            }
                        `}
                        render={handlePrivateRender}
                    />
                </Route>
            </>,
        ),
        render: createRender({}),
    });

    return <Router resolver={new Resolver(environment)} />;
}

export default App;
