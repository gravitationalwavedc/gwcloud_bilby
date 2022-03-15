import React, { useState, useEffect } from 'react';
import {createPaginationContainer, graphql} from 'react-relay';
import { Button, Card, Container, Col, Form, InputGroup, Row } from 'react-bootstrap';
import { HiOutlineSearch, HiOutlinePlus } from 'react-icons/hi';
import Link from 'found/Link';
import JobTable from '../Components/JobTable';

const RECORDS_PER_PAGE = 100;

const MyJobs = ({data, match, router,relay}) => {
    const [search, setSearch] = useState('');
    const [timeRange, setTimeRange] = useState('all');
    const [order, setOrder] = useState();
    const [direction, setDirection] = useState('descending');

    useEffect(() => handleSearchChange(), [search, timeRange, direction, order]);

    const handleSearchChange = () => {
        const refetchVariables = {
            count: RECORDS_PER_PAGE,
            search: search,
            timeRange: timeRange,
            orderBy: order,
            direction: direction
        };
        relay.refetchConnection(1, null, refetchVariables);
    };

    const loadMore = () => {
        if (relay.hasMore()) {
            relay.loadMore(RECORDS_PER_PAGE);
        }
    };

    const timeOptions = [
        {text: 'Any time', value: 'all'},
        {text: 'Past 24 hours', value: '1d'},
        {text: 'Past week', value: '1w'},
        {text: 'Past month', value: '1m'},
        {text: 'Past year', value: '1y'},
    ];

    return (
        <Container fluid className="pb-3">
            <Col md={{offset: 1, span: 10}}>
                <h1 className="pt-5 mb-4">
                    My Jobs
                    <span className="float-right">
                        <Link 
                            as={Button}
                            variant="outline-primary"
                            to='/bilby/' 
                            exact 
                            match={match}
                            router={router}
                            className="mr-1">
                                Switch to public jobs
                        </Link>
                        <Link as={Button} to='/bilby/job-form/' exact match={match} router={router}>
                            <HiOutlinePlus size={18} className="mb-1 mr-1"/>
                                Start a new job 
                        </Link>
                    </span>
                </h1>
                <Card className="gw-form-card">
                    <Card.Body>
                        <Form onSubmit={e => e.preventDefault()}>
                            <Form.Row>
                                <Col lg={3}>
                                    <Form.Group controlId="searchJobs" className="form-initial-height">
                                        <Form.Label srOnly>
                                            Search
                                        </Form.Label>
                                        <InputGroup>
                                            <InputGroup.Prepend>
                                                <InputGroup.Text>
                                                    <HiOutlineSearch />
                                                </InputGroup.Text>
                                            </InputGroup.Prepend>
                                            <Form.Control 
                                                placeholder="Find a job..." 
                                                value={search} 
                                                onChange={({target}) => setSearch(target.value)} />
                                        </InputGroup>
                                    </Form.Group>
                                </Col>
                                <Col lg={2}>
                                    <Form.Group controlId="timeRange" className="form-initial-height">
                                        <Form.Label srOnly>
                                            Time
                                        </Form.Label>
                                        <Form.Control 
                                            as="select" 
                                            value={timeRange} 
                                            onChange={({target}) => setTimeRange(target.value)} 
                                            custom>
                                            {timeOptions.map(
                                                option => 
                                                    <option key={option.value} value={option.value}>
                                                        {option.text}
                                                    </option>)}
                                        </Form.Control>
                                    </Form.Group>
                                </Col>
                            </Form.Row>
                        </Form>
                        <Row className="mt-4">
                            <Col>
                                <JobTable
                                    data={data.bilbyJobs} 
                                    setOrder={setOrder} 
                                    order={order} 
                                    setDirection={setDirection} 
                                    direction={direction}
                                    match={match}
                                    router={router}
                                    hasMore={relay.hasMore()}
                                    loadMore={loadMore}
                                    myJobs={true}
                                />
                            </Col>
                        </Row>
                    </Card.Body>
                </Card>
            </Col>
        </Container>
    );
};

export default createPaginationContainer(MyJobs,
    {
        data: graphql`
            fragment MyJobs_data on Query {
                bilbyJobs(
                    first: $count,
                    after: $cursor,
                    orderBy: $orderBy
                ) @connection(key: "MyJobs_bilbyJobs") {
                    edges {
                        node {
                            id
                            name
                            description
                            lastUpdated
                            jobStatus {
                                name
                            }
                            labels {
                                name
                            }
                            eventId {
                                triggerId
                                eventId
                                nickname
                            }
                        }
                    }
                  }
            }
        `,
    },
    {
        direction: 'forward',
        query: graphql`
            query MyJobsForwardQuery(
                $count: Int!,
                $cursor: String,
                $orderBy: String
            ) {
              ...MyJobs_data
            }
        `,
        getConnectionFromProps(props) {
            return props.data && props.data.bilbyJobs;
        },

        getFragmentVariables(previousVariables, totalCount) {
            return {
                ...previousVariables,
                count: totalCount
            };
        },

        getVariables(props, {count, cursor}, {orderBy}) {
            return {
                count,
                cursor,
                orderBy,
            };
        }
    }
);
