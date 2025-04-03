import EditableText from './EditableText';
import { graphql } from 'react-relay';
import { commitMutation } from 'relay-runtime';
import environment from '../../environment';

const mutation = graphql`
    mutation EditableDescriptionMutation($input: UpdateBilbyJobMutationInput!) {
        updateBilbyJob(input: $input) {
            result
            jobId
        }
    }
`;

const EditableDescription = ({ modifiable, value, jobId }) => {
  const handleSaveDescription = (newValue) => {
    const variables = {
      input: {
        jobId: jobId,
        description: newValue,
      },
    };

    commitMutation(environment, {
      mutation: mutation,
      variables: variables,
    });
  };

  return (
    <>
      {modifiable ? (
        <EditableText
          name="description"
          type="textarea"
          value={value}
          onSave={(value) => handleSaveDescription(value)}
          viewProps={{ className: 'p' }}
        />
      ) : (
        <p>{value}</p>
      )}
    </>
  );
};

export default EditableDescription;
