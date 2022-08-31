import React, { useState } from 'react';
import {commitMutation} from 'relay-runtime';
import {graphql} from 'react-relay';
import {harnessApi} from '../index';
import { Container, Col, Row, Tab, Nav } from 'react-bootstrap';
import { useFormik } from 'formik';
import JobTitle from '../Components/Forms/JobTitle';
import DataForm from '../Components/Forms/DataForm';
import SignalForm from '../Components/Forms/SignalForm';
import PriorsForm from '../Components/Forms/PriorsForm';
import ReviewJob from '../Components/Forms/ReviewJob';
import initialValues from '../Components/Forms/initialValues';
import validationSchema from '../Components/Forms/validationSchema';

const submitMutation = graphql`
  mutation NewJobMutation($input: BilbyJobMutationInput!) {
    newBilbyJob(input: $input) {
      result {
        jobId
      }
    }
  }
`;

const NewJob = ({initialValues, router, data}) => {
    const [key, setKey] = useState('data');

    const formik = useFormik({
        initialValues: initialValues,
        onSubmit: values => handleJobSubmission(values),
        validationSchema: validationSchema,
    });

    const handleJobSubmission = (values) => {
    // The mutation requires all number values to be strings.
        Object.entries(values)
            .filter(([key, value]) => typeof(value) === 'number') // eslint-disable-line no-unused-vars
            .map(([key, value]) => values[key] = value.toString());

        const variables = {
            input: {
                params: {
                    details: {
                        name: values.name,
                        description: values.description,
                        private: false
                    },

                    data: {
                        dataChoice: values.dataChoice,

                        triggerTime: values.triggerTime,

                        channels: {
                            hanfordChannel: values.hanfordChannel,
                            livingstonChannel: values.livingstonChannel,
                            virgoChannel: values.virgoChannel,
                        },

                        eventId: values.eventId ? values.eventId.eventId : null
                    },

                    detector: {
                        hanford: values.hanford,
                        hanfordMinimumFrequency: values.hanfordMinimumFrequency,
                        hanfordMaximumFrequency: values.hanfordMaximumFrequency,

                        livingston: values.livingston,
                        livingstonMinimumFrequency: values.livingstonMinimumFrequency,
                        livingstonMaximumFrequency: values.livingstonMaximumFrequency,

                        virgo: values.virgo,
                        virgoMinimumFrequency: values.virgoMinimumFrequency,
                        virgoMaximumFrequency: values.virgoMaximumFrequency,

                        duration: values.signalDuration,
                        samplingFrequency: values.samplingFrequency,
                    },

                    prior: {
                        priorDefault: values.priorChoice
                    },

                    sampler: {
                        nlive: values.nlive,
                        nact: values.nact,
                        maxmcmc: values.maxmcmc,
                        walks: values.walks,
                        dlogz: values.dlogz,
                        cpus: '1',
                        samplerChoice: 'dynesty',
                    },

                    waveform: {
                        model: values.signalChoice
                    },
                }
            }
        };

        commitMutation(harnessApi.getEnvironment('bilby'), {
            mutation: submitMutation,
            variables: variables,
            onCompleted: (response, errors) => {
                if (!errors) {
                    router.replace(`/bilby/job-results/${response.newBilbyJob.result.jobId}/`);
                }
            },
        });
    };

    return (
        <Container fluid>
            <Row>
                <Col md={2}/>
                <Col md={8} style={{minHeight: '110px'}}>
                    <JobTitle formik={formik} />
                </Col>
            </Row>
            <Tab.Container id="jobForm" activeKey={key} onSelect={(key) => setKey(key)}>
                <Row>
                    <Col md={2}>
                        <Nav className="flex-column">
                            <Nav.Item>
                                <Nav.Link eventKey="data">
                                    <h5>Data</h5>
                                    <p>Type and detectors</p>
                                </Nav.Link>
                            </Nav.Item>
                            <Nav.Item>
                                <Nav.Link eventKey="signal">
                                    <h5>Signal</h5>
                                    <p>Injection type and details</p>
                                </Nav.Link>
                            </Nav.Item>
                            <Nav.Item>
                                <Nav.Link eventKey="priorsAndSampler">
                                    <h5>Priors & Sampler</h5>
                                    <p>Default prior and sampler parameters</p>
                                </Nav.Link>
                            </Nav.Item>
                            <Nav.Item>
                                <Nav.Link eventKey="review">
                                    <h5>Review</h5>
                                    <p>Finalise and start your job</p>
                                </Nav.Link>
                            </Nav.Item>
                        </Nav>
                    </Col>
                    <Col md={8}>
                        <Tab.Content>
                            <Tab.Pane eventKey="data">
                                <DataForm formik={formik} handlePageChange={setKey} data={data}/>
                            </Tab.Pane>
                            <Tab.Pane data-testid="signalPane" eventKey="signal">
                                <SignalForm formik={formik} handlePageChange={setKey}/>
                            </Tab.Pane>
                            <Tab.Pane eventKey="priorsAndSampler">
                                <PriorsForm formik={formik} handlePageChange={setKey}/>
                            </Tab.Pane>
                            <Tab.Pane eventKey="review">
                                <ReviewJob
                                    formik={formik}
                                    values={formik.values}
                                    handleSubmit={formik.handleSubmit}/>
                            </Tab.Pane>
                        </Tab.Content>
                    </Col>
                </Row>
            </Tab.Container>
        </Container>
    );
};

NewJob.defaultProps = {
    initialValues: initialValues
};

export default NewJob;
