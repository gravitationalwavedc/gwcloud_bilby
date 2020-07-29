import {harnessApi} from "../../../index";
import { commitMutation, graphql } from "react-relay";

function UpdateBilbyJob(variables, callback) {
    commitMutation(harnessApi.getEnvironment("bilby"), {
        mutation: graphql`mutation UpdateBilbyJobMutation($jobId: ID!, $private: Boolean, $labels: [String])
            {
              updateBilbyJob(input: {jobId: $jobId, private: $private, labels: $labels}) 
              {
                result
              }
            }`,
        optimisticResponse: {
            updateBilbyJob: {
                result: 'Job saved!'
            }
        },
        variables: variables,
        onCompleted: (response, errors) => {
            if (errors) {
                callback(false, errors)
                console.log(errors)
            }
            else {
                callback(true, response.updateBilbyJob.result)
                console.log(response)
            }
        },
    })
}

export default UpdateBilbyJob