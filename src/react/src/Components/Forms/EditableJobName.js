import React, { useState } from "react";
import EditableText from "./EditableText";
import { graphql } from "react-relay";
import { commitMutation } from "relay-runtime";
import { harnessApi } from "../../index";
import validationSchema from "./validationSchema";

const mutation = graphql`
  mutation EditableJobNameMutation($input: UpdateBilbyJobMutationInput!) {
    updateBilbyJob(input: $input) {
      result
      jobId
    }
  }
`;

const EditableJobName = ({ modifiable, value, jobId }) => {
  const [errors, setErrors] = useState();

  const handleSaveJobName = async (newValue) => {
    try {
      await validationSchema.validateAt("name", { name: newValue });
    } catch (error) {
      setErrors(error.message);
      return;
    }

    const variables = {
      input: {
        jobId: jobId,
        name: newValue,
      },
    };

    commitMutation(harnessApi.getEnvironment("bilby"), {
      mutation: mutation,
      variables: variables,
      onCompleted: (response, errors) => {
        if (errors) {
          setErrors(errors.map((error) => error.message));
        } else {
          // clear errors if everything worked.
          setErrors();
        }
      },
    });
  };

  return (
    <React.Fragment>
      {modifiable ? (
        <EditableText
          name="job-name"
          value={value}
          onSave={(value) => handleSaveJobName(value)}
          viewProps={{ className: "h1" }}
          hint="You can only use letters, numbers, underscores, and hyphens."
          errors={errors}
        />
      ) : (
        <h1>{value}</h1>
      )}
    </React.Fragment>
  );
};

export default EditableJobName;
