import React, {useState} from 'react';
import { harnessApi } from '../index';
import { graphql, createFragmentContainer } from 'react-relay';
import { Row, Nav, Col, Button, Container, Tab, Toast } from 'react-bootstrap';
import moment from 'moment';
import Files from '../Components/Results/Files';
import Parameters from '../Components/Results/Parameters';
import Link from 'found/Link';
import LabelDropdown from '../Components/Results/LabelDropdown';
import EventIDDropdown from '../Components/Results/EventIDDropdown';
import PrivacyToggle from '../Components/Results/PrivacyToggle';
import StatusDisplay from '../Components/Results/StatusDisplay';
import SaveToast from '../Components/Results/SaveToast';

const ViewJob = (props) => {
    const [saved, setSaved] = useState(false);
    const [showNotification, setShowNotification] = useState(false);
    const [toastMessage, setToastMessage] = useState(null);

    const onSave = (saved, message) => {
        setSaved(saved)
        setToastMessage(message)
        setShowNotification(true);
    };

    const { params, lastUpdated, userId } = props.data.bilbyJob;
    const { details } = params;

    const updated = moment.utc(lastUpdated, 'YYYY-MM-DD HH:mm:ss UTC').local().format('llll');

    const modifiable = harnessApi.currentUser.userId == userId

    return (
        <Container className="pt-5" fluid>
            <SaveToast
                saved={saved}
                show={showNotification} 
                message={toastMessage} 
                onClose={() => setShowNotification(false)}
            />
            <Row className="mb-3">
                <Col md={2} />
                <Col md={6}>
                    <h1>{details.name}</h1>
                    <LabelDropdown jobId={props.match.params.jobId} data={props.data} onUpdate={onSave} modifiable={modifiable}/>
                    <StatusDisplay name={props.data.bilbyJob.jobStatus.name} date={updated}/>
                </Col>
                <Col md={2}>
                    <Link as={Button} to={{
                        pathname: '/bilby/job-form/duplicate/',
                        state: {
                            jobId: props.match.params.jobId
                        }
                    }} className="float-right" activeClassName="selected" exact match={props.match} router={props.router}>
                      Duplicate job
                    </Link>
                </Col>
            </Row>
            <Row className="mb-3">
                <Col md={2} />
                <Col md={8}>
                    <p className="mb-0">{details.description}</p>
                    <EventIDDropdown jobId={props.match.params.jobId} data={props.data} onUpdate={onSave} modifiable={modifiable}/>

                </Col>
            </Row>
            <Row className="mb-3">
                <Col md={2} />
                <Col md={8}>
                    <PrivacyToggle 
                        jobId={props.match.params.jobId} 
                        data={props.data.bilbyJob}
                        onUpdate={onSave}
                        modifiable={modifiable}
                    />
                </Col>
            </Row>
            <Tab.Container id="jobResultsTabs" defaultActiveKey="parameters">
                <Row>
                    <Col md={2}>
                        <Nav className="flex-column">
                            <Nav.Item>
                                <Nav.Link eventKey="parameters">
                                    <h5>Parameters</h5>
                                </Nav.Link>
                            </Nav.Item>
                            <Nav.Item>
                                <Nav.Link eventKey="results">
                                    <h5>Results</h5>
                                </Nav.Link>
                            </Nav.Item>
                        </Nav>
                    </Col>
                    <Col md={8}>
                        <Tab.Content>
                            <Tab.Pane eventKey="parameters">
                                <Parameters params={params} {...props}/>
                            </Tab.Pane>
                            <Tab.Pane eventKey="results">
                                <Files {...props}/>
                            </Tab.Pane>
                        </Tab.Content>
                    </Col>
                </Row>
            </Tab.Container>
            <Files {...props} hidden style={{display:'none'}}/>
        </Container>
    );
};

export default createFragmentContainer(ViewJob,
    {
        data: graphql`
            fragment ViewJob_data on Query @argumentDefinitions(
                jobId: {type: "ID!"}
            ){
                bilbyJob (id: $jobId) {
                    id
                    userId
                    lastUpdated
                    ...PrivacyToggle_data
                    jobStatus {
                        name
                        number
                        date
                    }
                    params {
                        details {
                            name
                            description
                            private
                        }
                        ...Parameters_params
                    }
                }
                ...LabelDropdown_data @arguments(jobId: $jobId)
                ...EventIDDropdown_data @arguments(jobId: $jobId)
            }
        `,
    },
);
