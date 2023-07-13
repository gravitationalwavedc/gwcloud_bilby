import React, { useState, useEffect, useRef } from "react";
import { createFragmentContainer, commitMutation, graphql } from "react-relay";
import { Row, Col, Dropdown } from "react-bootstrap";
import { harnessApi } from "../../index";
import LabelBadge from "./LabelBadge";
import CustomToggle from "./CustomToggle";

const LabelDropdown = ({ data, jobId, onUpdate, modifiable }) => {
  const [labels, setLabels] = useState(
    data.bilbyJob.labels.map((label) => label.name)
  );
  const isMounted = useRef();
  const labelChoices = data.allLabels.edges.filter(
    ({ node }) => !labels.includes(node.name) && !node.protected
  );

  useEffect(() => {
    if (isMounted.current) {
      updateJob(
        {
          jobId: jobId,
          labels: labels,
        },
        onUpdate
      );
    } else {
      isMounted.current = true;
    }
  }, [labels]);

  return (
    <Row className="mb-1">
      {labels.length > 0 && (
        <Col md="auto" className="my-auto">
          {labels.map((name) => (
            <LabelBadge
              key={name}
              name={name}
              dismissable={modifiable}
              onDismiss={() =>
                setLabels(labels.filter((label) => label !== name))
              }
            />
          ))}
        </Col>
      )}
      {labelChoices.length > 0 && modifiable && (
        <Col className="my-auto">
          <Dropdown>
            <Dropdown.Toggle as={CustomToggle} id="labelControl">
              Add label
            </Dropdown.Toggle>
            <Dropdown.Menu>
              {labelChoices.map(({ node: { name, description } }) => (
                <Dropdown.Item
                  key={name}
                  value={name}
                  onClick={() => setLabels([name, ...labels])}
                >
                  <h6>{name}</h6>
                  <p>{description}</p>
                </Dropdown.Item>
              ))}
            </Dropdown.Menu>
          </Dropdown>
        </Col>
      )}
    </Row>
  );
};

const updateJob = (variables, callback) =>
  commitMutation(harnessApi.getEnvironment("bilby"), {
    mutation: graphql`
      mutation LabelDropdownMutation(
        $jobId: ID!
        $private: Boolean
        $labels: [String]
      ) {
        updateBilbyJob(
          input: { jobId: $jobId, private: $private, labels: $labels }
        ) {
          result
        }
      }
    `,
    optimisticResponse: {
      updateBilbyJob: {
        result: "Job saved!",
      },
    },
    variables: variables,
    onCompleted: (response, errors) => {
      if (errors) {
        callback(false, errors);
      } else {
        callback(true, "Job labels updated!");
      }
    },
  });

export default createFragmentContainer(LabelDropdown, {
  data: graphql`
    fragment LabelDropdown_data on Query
    @argumentDefinitions(jobId: { type: "ID!" }) {
      bilbyJob(id: $jobId) {
        labels {
          name
        }
      }

      allLabels {
        edges {
          node {
            name
            description
            protected
          }
        }
      }
    }
  `,
});
