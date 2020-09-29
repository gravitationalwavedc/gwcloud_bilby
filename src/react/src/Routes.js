import React from "react";
import {Route} from 'found'
import StepForm from "./Components/Forms/StepForm";
import UserJobList from "./Components/List/UserJobList";
import PublicJobList from "./Components/List/PublicJobList";
import {graphql} from "react-relay";
import {harnessApi} from "./index";
import BilbyJobResults from "./Pages/BilbyJobResults";
import Loading from "./Components/Loading";
import {RedirectException} from "found";

const handleRender = ({Component, props}) => {
  if (!Component || !props)
      return <Loading/>;

  if (!harnessApi.hasAuthToken())
      throw new RedirectException("/auth/?next=" + props.match.location.pathname, 401);
  
  return <Component data={props} {...props}/>;
};

function getRoutes() {
    return (
        <Route>
            <Route
                Component={PublicJobList}
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
                    ...PublicJobList_data
                }
              `}
              prepareVariables={params => ({
                  ...params,
                  timeRange: '1d',
                  count: 10
              })}
              environment={harnessApi.getEnvironment('bilby')}
              Component={PublicJobList}
              render={handleRender}/>
            <Route
                path="job-form"
                query={graphql`
                    query Routes_JobForm_Query ($jobId: ID!){
                      ...StepForm_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(params, {location}) => ({
                    ...params,
                    jobId: location.state && location.state.jobId ? location.state.jobId : ""
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={StepForm}
                render={handleRender}/>
            <Route
                path="job-list"
                query={graphql`
                    query Routes_JobList_Query(
                      $count: Int!,
                      $cursor: String,
                      $orderBy: String
                    ) {
                      ...UserJobList_data
                    }
                `}
                prepareVariables={params => ({
                    ...params,
                    count: 10,
                    orderBy: 'lastUpdated'
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={UserJobList}
                render={handleRender}/>
            <Route
                path="job-results/:jobId/"
                environment={harnessApi.getEnvironment('bilby')}
                Component={BilbyJobResults}
                query={graphql`
                    query Routes_BilbyJobResults_Query ($jobId: ID!){
                      ...BilbyJobResults_data @arguments(jobId: $jobId)
                    }
                `}
                prepareVariables={(params, {location}) => ({
                    ...params,
                    jobId: params.jobId
                })}
                render={handleRender}
            />
        </Route>
    )
}

export default getRoutes;
