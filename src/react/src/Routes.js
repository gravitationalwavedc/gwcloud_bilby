import React from "react";
import {Route} from 'found'
import BilbyJobForm from "./Pages/BilbyJobForm";
import BilbyJobList from "./Pages/BilbyJobList";
import {graphql} from "react-relay";
import {harnessApi} from "./index";
import BilbyHomePage from "./Pages/BilbyHomePage";
import BilbyJobResults from "./Pages/BilbyJobResults";

function getRoutes() {
    return (
        <Route>
            <Route
                Component={BilbyHomePage}
                query={graphql`
                query Routes_HomePage_Query (
                  $count: Int!,
                  $cursor: String,
                  $orderBy: String
                ) {
                    gwclouduser {
                      username
                    }
                    ...BilbyHomePage_data
                }
              `}
              prepareVariables={params => ({
                ...params,
                count: 5,
                orderBy: '-last_updated'
              })}
              environment={harnessApi.getEnvironment('bilby')}
              Component={BilbyHomePage}
              render={({Component, props, retry, error}) => {
                  if (!Component || !props)
                      return <div>Loading...</div>;
                  console.log('hello',props)
                  return <Component data={props} match={props.match} router={props.router}/>
            }}/>
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
                Component={BilbyJobForm}
                render={({Component, props, retry, error}) => {
                    if (!Component || !props)
                        return <div>Loading...</div>;

                    return <Component {...props}/>
                }}/>
            <Route
                path="job-list"
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
                    count: 10,
                    orderBy: 'last_updated'
                })}
                environment={harnessApi.getEnvironment('bilby')}
                Component={BilbyJobList}
                render={({Component, props, retry, error}) => {
                    if (!Component || !props)
                        return <div>Loading...</div>;
                    console.log('hello', props)
                    return <Component data={props} {...props}/>
                }}/>
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
                render={({Component, props, retry, error}) => {
                    if (!Component || !props)
                        return <div>Loading...</div>;

                    return <Component data={props} {...props}/>
                }}
            />
        </Route>
    )
}

export default getRoutes;