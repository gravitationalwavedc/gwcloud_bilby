import React from "react";
import {Route} from 'found'
import HelloAgain from "./Pages/HelloAgain";
import Hello from "./Pages/Hello";
import BilbyJobForm from "./Pages/BilbyJobForm";
import BilbyJobList from "./Pages/BilbyJobList";
import {graphql} from "react-relay";
import {harnessApi} from "./index";
import BilbyHomePage from "./Pages/BilbyHomePage";

function getRoutes() {
    return (
        <Route>
            <Route
                Component={BilbyHomePage}
                query={graphql`
                   query Routes_UserDetails_Query {
                     gwclouduser {
                       username
                     }
                   }
                `}
                environment={harnessApi.getEnvironment('bilby')}
            />
            <Route path="job-form" 
              query={graphql`
                query Routes_JobForm_Query ($jobId: ID!){
                  ...StepForm_data @arguments(jobId: $jobId)
                  ...StartForm_jobNames
                }
              `}
              prepareVariables={(params, {location}) => ({
                ...params,
                jobId: location.state && location.state.jobId ? location.state.jobId : "" 
              })}
              environment={harnessApi.getEnvironment('bilby')}
              Component={BilbyJobForm}
              render={({Component, props, retry, error}) => {
                  if (!Component || !props)
                      return <div>Loading...</div>;

                  return <Component {...props}/>
              }}/>
            <Route path="job-list"
              query={graphql`
                query Routes_JobList_Query(
                  $count: Int!,
                  $cursor: String,
                  $orderBy: String
                ) {
                  ...BilbyJobList_data
                }
              `}
              prepareVariables={params => ({
                ...params,
                count: 1,
                orderBy: 'last_updated'
              })}
              environment={harnessApi.getEnvironment('bilby')}
              Component={BilbyJobList}
              render={({Component, props, retry, error}) => {
                  if (!Component || !props)
                      return <div>Loading...</div>;

                  return <Component data={props} {...props}/>
              }}/>
        </Route>
    )
}

export default getRoutes;