import React from 'react';
import JobBadges from './JobBadges';
import { Row, Col, Badge } from 'react-bootstrap';
import Link from 'found/Link';
import EventIDCell from './EventIDCell';
import JobNameCell from './JobNameCell';

const JobTableBody = ({data, myJobs, match, router}) => 
    <>
        {data && data.edges.length > 0 ? 
            data.edges.map(({node}) => 
                <Row key={node.id} className="mb-4 align-items-center">
                    <EventIDCell eventID={node.eventId} />
                    <JobNameCell author={node.user} jobName={node.name} description={node.description} />
                    <Col md={3} className="text-center">
                        <JobBadges labels={[node.jobStatus, ...node.labels]} />
                    </Col>
                    <Col md={1} className="text-center">
                        <Link 
                            key={node.id}
                            size="sm" 
                            variant="outline-primary" 
                            to={{pathname: '/bilby/job-results/' + node.id + '/'}} 
                            activeClassName="selected" 
                            exact 
                            match={match} 
                            router={router}>
                              View
                        </Link>
                    </Col>
                </Row>) : 
            <Row>
                <Col>Create a new job or try searching &apos;Any time&apos;.</Col>
            </Row>
        }
    </>;

export default JobTableBody;
