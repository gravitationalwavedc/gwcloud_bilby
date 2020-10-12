import React, { useState } from 'react';
import { Redirect } from 'found';
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

const submitMutation = graphql`
  mutation NewJobMutation($input: BilbyJobMutationInput!) {
    newBilbyJob(input: $input) {
      result {
        jobId
      }
    }
  }
`;

const NewJob = ({initialValues, router}) => {
    const [title, setTitle] = useState(initialValues.name); 
    const [description, setDescription] = useState(initialValues.description);
    const [isPrivate] = useState(initialValues.private);
    const [key, setKey] = useState('data');

    const handleJobSubmission = (values) => {
    // The mutation requires all number values to be strings. 
        Object.entries(values)
            .filter(([key, value]) => typeof(value) === 'number')
            .map(([key, value]) => values[key] = value.toString());

        const variables = {
            input: {
                start: {
                    name: title,
                    description: description,
                    private: isPrivate, 
                },
                data: {
                    dataType: values.dataChoice,
                    dataChoice: values.dataChoice,
                    signalDuration: values.signalDuration,
                    samplingFrequency: values.samplingFrequency,
                    triggerTime: values.triggerTime,
                    hanford: values.hanford,
                    hanfordMinimumFrequency: values.hanfordMinimumFrequency,
                    hanfordMaximumFrequency: values.hanfordMaximumFrequency,
                    hanfordChannel: values.hanfordChannel,
                    livingston: values.livingston,
                    livingstonMinimumFrequency: values.livingstonMinimumFrequency,
                    livingstonMaximumFrequency: values.livingstonMaximumFrequency,
                    livingstonChannel: values.livingstonChannel,
                    virgo: values.virgo,
                    virgoMinimumFrequency: values.virgoMinimumFrequency,
                    virgoMaximumFrequency: values.virgoMaximumFrequency,
                    virgoChannel: values.virgoChannel,
                },
                signal: {
                    mass1: values.mass1,
                    mass2: values.mass2,
                    luminosityDistance: values.luminosityDistance,
                    psi: values.psi,
                    iota: values.iota,
                    phase: values.phase,
                    mergerTime: values.mergerTime,
                    ra: values.ra,
                    dec: values.dec,
                    signalChoice: values.signalChoice,
                    signalModel: 'none',
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
                prior: {
                    priorChoice: values.priorChoice
                },
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

    const formik = useFormik({
        initialValues: initialValues,
        onSubmit: values => handleJobSubmission(values)
    });

    return (
        <Container fluid>
            <Row className="mb-3">
                <Col md={2}/>
                <Col md={8} style={{minHeight: '110px'}}>
                    <JobTitle 
                        title={title} 
                        description={description} 
                        setTitle={setTitle} 
                        setDescription={setDescription} />
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
                                <DataForm formik={formik} handlePageChange={setKey}/>
                            </Tab.Pane>
                            <Tab.Pane data-testid="signalPane" eventKey="signal">
                                <SignalForm formik={formik} handlePageChange={setKey}/>
                            </Tab.Pane>
                            <Tab.Pane eventKey="priorsAndSampler">
                                <PriorsForm formik={formik} handlePageChange={setKey}/>
                            </Tab.Pane>
                            <Tab.Pane eventKey="review">
                                <ReviewJob values={formik.values} handleSubmit={formik.handleSubmit}/>
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
